#!/usr/bin/env python3
"""Approved-source clipping and separately gated publishing; no Vyro scraping/API assumptions."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
from urllib.parse import urljoin, urlsplit

import requests

ROOT = Path(__file__).resolve().parent
PLATFORMS = {"youtube", "instagram", "tiktok"}
MAX_BYTES = 2 * 1024**3


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def file_hash(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value):
        raise ValueError("Invalid source, clip or account identifier")
    return value


def sources(path):
    data = json.loads(Path(path).read_text())
    if data.get("version") != 1:
        raise ValueError("Unsupported configuration version")
    result = data["sources"]
    ids = [identifier(s["id"]) for s in result]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate source IDs")
    return result


def timestamp(value):
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("A timezone is required")
    return date


def validate_source(source, publishing=False, automatic=False, now=None):
    now = now or datetime.now(timezone.utc)
    identifier(source["id"])
    for field in ("enabled", "rights_confirmed", "editing_allowed"):
        if source.get(field) is not True:
            raise ValueError(f"Source requires {field}=true")
    for field in ("creator", "campaign_url", "attribution", "permission_reference", "rules"):
        if not isinstance(source.get(field), str) or not source[field].strip():
            raise ValueError(f"Source requires {field}")
    archival = source.get("rights_type") == "public_domain_archive"
    if archival:
        if source.get("license_url") != "http://creativecommons.org/licenses/publicdomain/":
            raise ValueError("Unexpected archive rights statement")
    else:
        if timestamp(source["expires_at"]) <= now:
            raise ValueError("Source/campaign has expired")
        if source.get("campaign_status") != "active":
            raise ValueError("Campaign is not active")
    if not re.fullmatch(r"[a-f0-9]{64}", source.get("sha256", "")):
        raise ValueError("Approved source needs a SHA-256 fingerprint")
    allowed = source.get("platforms", [])
    if not allowed or not set(allowed) <= PLATFORMS or len(set(allowed)) != len(allowed):
        raise ValueError("Invalid campaign platforms")
    if not 5 <= source.get("min_seconds", 25) <= source.get("max_seconds", 60) <= 60:
        raise ValueError("Clip duration must be between 5 and 60 seconds")
    if not 1 <= source.get("max_clips", 3) <= 3:
        raise ValueError("At most three clips per source/run")
    for field in ("branded_content", "made_for_kids"):
        if not isinstance(source.get(field), bool):
            raise ValueError(f"Review {field}")
    if source["branded_content"] and not source.get("disclosure", "").strip():
        raise ValueError("Paid campaign requires disclosure text")
    if publishing and not archival:
        # No supported live Vyro API is verified. Require a recent human status check.
        checked = timestamp(source["status_checked_at"])
        if not now - timedelta(hours=24) <= checked <= now:
            raise ValueError("Campaign status needs rechecking (24-hour publication window)")
    if automatic and source.get("auto_publish_approved") is not True:
        raise ValueError("This campaign is not approved for automatic publishing")


def public_https(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Expected public HTTPS media URL without embedded credentials")
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("Non-public media hosts are not permitted")


def download(url, target, max_bytes=MAX_BYTES):
    # Do not log signed URLs, response bodies or request exceptions.
    for _ in range(6):
        public_https(url)
        with requests.get(url, stream=True, allow_redirects=False, timeout=(15, 60)) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                url = urljoin(url, response.headers["Location"])
                continue
            if response.status_code != 200:
                raise RuntimeError(f"Source download HTTP {response.status_code}; refresh signed URL")
            if int(response.headers.get("Content-Length", "0")) > max_bytes:
                raise ValueError("Source exceeds 2 GiB")
            size = 0
            with open(target, "wb") as stream:
                for chunk in response.iter_content(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Source exceeds 2 GiB")
                    stream.write(chunk)
            return
    raise ValueError("Too many source redirects")


def probe(path):
    output = subprocess.check_output([
        "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-show_format",
        "-show_streams", "-of", "json", str(Path(path).resolve()),
    ])
    data = json.loads(output)
    duration = float(data["format"]["duration"])
    kinds = {s["codec_type"] for s in data["streams"]}
    if not math.isfinite(duration) or not 5 <= duration <= 3600 or not {"video", "audio"} <= kinds:
        raise ValueError("Media must have audio/video and be 5 seconds to 60 minutes")
    return data, duration


def validate_transcript(segments, duration):
    clean, last = [], 0.0
    for item in segments:
        start, end = float(item["start"]), float(item["end"])
        text = " ".join(str(item["text"]).split())
        if not all(math.isfinite(t) for t in (start, end)) or not 0 <= start < end <= duration + 0.1 or start < last:
            raise ValueError("Transcript has invalid/overlapping timestamps")
        last = end
        if text:
            clean.append({"start": start, "end": min(end, duration), "text": text})
    if not clean:
        raise ValueError("No speech found")
    return clean


def transcribe(path):
    from faster_whisper import WhisperModel
    model = WhisperModel("base.en", device="cpu", compute_type="int8", cpu_threads=2)
    segments, _ = model.transcribe(str(path), language="en", vad_filter=True, beam_size=5)
    return [{"start": s.start, "end": s.end, "text": s.text} for s in segments]


def select_clips(segments, source):
    """Deterministic hook/speech-density ranking, not a prediction of viral success."""
    candidates = []
    minimum, maximum = source.get("min_seconds", 25), source.get("max_seconds", 60)
    for i, first in enumerate(segments):
        if i and not re.search(r'[.!?][\"\u201d\u2019]*$', segments[i - 1]["text"]):
            continue
        for j in range(i, len(segments)):
            length = segments[j]["end"] - first["start"]
            if length > maximum:
                break
            if length < minimum or not re.search(r'[.!?][\"\u201d\u2019]*$', segments[j]["text"]):
                continue
            selected = segments[i:j + 1]
            text = " ".join(s["text"] for s in selected)
            hook = first["text"].lower()
            score = sum(w in hook for w in ("why", "how", "what", "imagine", "secret", "never", "challenge")) * 3
            score += min(len(text.split()) / length, 3) - abs(length - (minimum + maximum) / 2) / maximum
            clip_id = digest({"media": source["sha256"], "start": first["start"], "end": selected[-1]["end"]})[:20]
            candidates.append({"id": clip_id, "start": first["start"], "end": selected[-1]["end"],
                               "score": round(score, 3), "segments": selected,
                               "title": first["text"][:90], "text": text})
    result = []
    for candidate in sorted(candidates, key=lambda x: (-x["score"], x["start"])):
        if all(candidate["end"] <= c["start"] or candidate["start"] >= c["end"] for c in result):
            result.append(candidate)
        if len(result) >= source.get("max_clips", 3):
            break
    if not result:
        raise ValueError("No complete speech segments fit the duration; review transcript/range")
    return result


def ass_time(seconds):
    ticks = round(max(0, seconds) * 100)
    return f"{ticks // 360000}:{ticks // 6000 % 60:02}:{ticks // 100 % 60:02}.{ticks % 100:02}"


def safe_ass(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def captions(clip, path):
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Montserrat,54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,100,100,320,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for segment in clip["segments"]:
        words = safe_ass(segment["text"]).split()
        chunks = [" ".join(words[i:i + 7]) for i in range(0, len(words), 7)]
        for i, chunk in enumerate(chunks):
            length = (segment["end"] - segment["start"]) / len(chunks)
            start = segment["start"] - clip["start"] + i * length
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(start + length)},Default,,0,0,0,,{chunk}")
    path.write_text(header + "\n".join(lines) + "\n")


def render(media, clip, directory):
    directory.mkdir(parents=True, exist_ok=True)
    subtitle = directory / "captions.ass"
    captions(clip, subtitle)
    output = directory / "clip.mp4"
    # Fit rather than crop to preserve subjects and source watermarks.
    with tempfile.TemporaryDirectory(prefix="clip-render-") as scratch:
        shutil.copytree(ROOT / "fonts", Path(scratch) / "fonts")
        shutil.copy(subtitle, Path(scratch) / "captions.ass")
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-protocol_whitelist", "file,pipe",
            "-ss", str(clip["start"]), "-i", str(Path(media).resolve()),
            "-t", str(clip["end"] - clip["start"]), "-map", "0:v:0", "-map", "0:a:0",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                   "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,ass=captions.ass:fontsdir=fonts",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-r", "30", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output.resolve()),
        ], cwd=scratch, check=True, timeout=600)
    data, duration = probe(output)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    if (video["width"], video["height"]) != (1080, 1920) or abs(duration - (clip["end"] - clip["start"])) > 0.3:
        raise ValueError("Rendered clip failed verification")
    return output


def preview(args):
    selected = [s for s in sources(args.config) if s.get("enabled") is True]
    if args.source:
        selected = [s for s in selected if s["id"] == args.source]
        if not selected:
            raise ValueError("Requested source is unknown or disabled")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"version": 1, "commit": os.environ.get("GITHUB_SHA", "local"), "clips": []}
    if len(selected) > 3:
        raise ValueError("Select a source; at most three sources may run together")
    for source in selected:
        validate_source(source)
        with tempfile.TemporaryDirectory(prefix="clip-source-") as scratch:
            media = Path(scratch) / "source.mp4"
            if args.media:
                if len(selected) != 1:
                    raise ValueError("Local media requires exactly one source")
                media = Path(args.media)
            else:
                urls = json.loads(os.environ.get("CLIP_SOURCE_URLS_JSON", "{}"))
                if not urls.get(source["id"]):
                    raise ValueError("Approved download missing from CLIP_SOURCE_URLS_JSON")
                download(urls[source["id"]], media)
            if file_hash(media) != source["sha256"]:
                raise ValueError("Media differs from the approved fingerprint")
            _, duration = probe(media)
            segments = json.loads(Path(args.transcript).read_text()) if args.transcript else transcribe(media)
            segments = validate_transcript(segments, duration)
            for clip in select_clips(segments, source):
                output = render(media, clip, out / clip["id"])
                caption = f"{clip['title']}\n\n{source['attribution']}"
                caption += "\n" + source.get("disclosure", "")
                caption += "\n" + " ".join(source.get("hashtags", []))
                if len(caption) > 2000:
                    raise ValueError("Caption exceeds shared platform limit")
                manifest["clips"].append({**clip, "source_id": source["id"], "source_digest": digest(source),
                                          "sha256": file_hash(output), "caption": caption.strip()})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    summary = "# Creator clip previews\n\n"
    if not selected:
        summary += "No approved sources enabled. No videos downloaded, generated, or posted.\n"
    else:
        summary += "Review MP4s, captions, context, campaign rules and disclosure before enabling publishing.\n\n"
        for c in manifest["clips"]:
            summary += f"- `{c['id']}` — {c['source_id']}, {c['start']:.2f}–{c['end']:.2f}s\n"
    (out / "REVIEW.md").write_text(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
            stream.write(summary)
    print(summary)


def api_json(method, url, token, **kwargs):
    response = requests.request(method, url, headers={"Authorization": f"Bearer {token}"}, timeout=60, **kwargs)
    if not response.ok:
        raise RuntimeError(f"Service HTTP {response.status_code}; inspect provider before retrying")
    return response.json()


def github(method, endpoint, **kwargs):
    repo = os.environ["GITHUB_REPOSITORY"]
    return api_json(method, f"https://api.github.com/repos/{repo}/{endpoint}", os.environ["GH_TOKEN"], **kwargs)


def verify_run(run_id):
    if not str(run_id).isdigit():
        raise ValueError("Preview run ID must be numeric")
    run = github("GET", f"actions/runs/{run_id}")
    if (run["head_repository"]["full_name"] != os.environ["GITHUB_REPOSITORY"] or run["head_branch"] != "main"
            or run["path"] != ".github/workflows/daily-video.yml" or run["conclusion"] != "success"
            or run["event"] not in ("schedule", "workflow_dispatch")):
        raise ValueError("Only successful main-branch clip previews may publish")
    return run


def post_payload(source, clip, accounts, media_url):
    if not accounts or not set(accounts) <= set(source["platforms"]):
        raise ValueError("Destination is not permitted by the campaign")
    if len(set(accounts.values())) != len(accounts):
        raise ValueError("Duplicate destination IDs")
    configs = {
        "tiktok": {"caption": clip["caption"], "privacy_status": "public", "allow_comment": True,
                   "allow_duet": False, "allow_stitch": False, "is_ai_generated": source.get("synthetic_narration", False),
                   "disclose_branded_content": source["branded_content"]},
        "instagram": {"caption": clip["caption"], "placement": "reels", "share_to_feed": True},
        "youtube": {"title": clip["title"][:100], "description": clip["caption"], "localizations": {},
                    "privacy_status": "public", "made_for_kids": source["made_for_kids"],
                    "contains_synthetic_media": source.get("synthetic_narration", False)},
    }
    return {"external_id": f"creator-clip-{clip['id']}", "caption": clip["caption"],
            "social_accounts": list(accounts.values()), "media": [{"url": media_url}],
            "platform_configurations": {p: configs[p] for p in accounts}}


def reserved(clip_id):
    title, page = f"[clip-publication] {clip_id}", 1
    while True:
        issues = github("GET", "issues", params={"state": "all", "per_page": 100, "page": page})
        if any(issue["title"] == title for issue in issues):
            return True
        if len(issues) < 100:
            return False
        page += 1


def publish_one(args, clip, source):
    validate_source(source, publishing=True, automatic=args.automatic)
    if digest(source) != clip["source_digest"]:
        raise ValueError("Source/rules changed since preview; create a fresh preview")
    identifier(clip["id"])
    media = Path(args.output) / clip["id"] / "clip.mp4"
    if file_hash(media) != clip["sha256"]:
        raise ValueError("Preview fingerprint mismatch")
    accounts = json.loads(os.environ.get("CLIP_DESTINATIONS_JSON", "{}"))
    payload = post_payload(source, clip, accounts, "pending")
    key, base = os.environ["POSTFORME_API_KEY"], "https://api.postforme.dev/v1"
    for platform, account_id in accounts.items():
        identifier(account_id)
        account = api_json("GET", f"{base}/social-accounts/{account_id}", key)
        if account.get("platform") != platform or account.get("status") != "connected":
            raise ValueError("Social account is disconnected or does not match configured platform")
    # Serialized workflow reserves BEFORE side effects. Unknown failures never retry automatically.
    if reserved(clip["id"]):
        print(f"Skipping reserved clip {clip['id']}; inspect its publication issue.")
        return
    issue = github("POST", "issues", json={"title": f"[clip-publication] {clip['id']}", "body":
        f"Reserved. Preview run: {args.run_id}.\n\nIf still reserved, reconcile with Post for Me before retrying. "
        "Closing this issue does NOT clear the lock."})
    upload = api_json("POST", f"{base}/media/create-upload-url", key)
    public_https(upload["upload_url"])
    public_https(upload["media_url"])
    with open(media, "rb") as stream:
        response = requests.put(upload["upload_url"], data=stream, headers={"Content-Type": "video/mp4"}, timeout=300)
    if not response.ok:
        raise RuntimeError("Media upload failed; publication reservation retained")
    payload["media"] = [{"url": upload["media_url"]}]
    post = api_json("POST", f"{base}/social-posts", key, json=payload)
    if not post.get("id"):
        raise RuntimeError("Missing provider post ID; reconcile reservation manually")
    github("PATCH", f"issues/{issue['number']}", json={"body":
        f"Queued, not yet confirmed published.\n\nPost for Me ID: `{post['id']}`\n"
        f"Platforms: {', '.join(accounts)}\nPreview run: {args.run_id}\n\n"
        "Check provider delivery per platform. "
        "Do not repost the whole batch after a partial failure."})
    print(f"Queued; track delivery in publication issue #{issue['number']}.")


def publish(args):
    if os.environ.get("CLIP_PUBLISH_ENABLED") != "true" or not args.approved:
        raise ValueError("Publishing requires the master switch and explicit approval")
    if args.automatic and os.environ.get("CLIP_AUTO_PUBLISH_ENABLED") != "true":
        raise ValueError("Automatic publishing is disabled")
    run = verify_run(args.run_id)
    manifest = json.loads((Path(args.output) / "manifest.json").read_text())
    if manifest.get("version") != 1 or manifest["commit"] != run["head_sha"]:
        raise ValueError("Artifact does not match verified preview")
    configured = {s["id"]: s for s in sources(args.config)}
    if args.automatic:
        clips = [c for c in manifest["clips"] if configured[c["source_id"]].get("auto_publish_approved") is True]
        clips = [c for c in clips if not reserved(c["id"])][:1]
    else:
        identifier(args.clip)
        clips = [c for c in manifest["clips"] if c["id"] == args.clip]
        if len(clips) != 1:
            raise ValueError("Clip not found uniquely")
    for clip in clips:
        publish_one(args, clip, configured[clip["source_id"]])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["preview", "publish", "verify-run"])
    parser.add_argument("--config", default="clips/sources.json")
    parser.add_argument("--output", default="clip-output")
    parser.add_argument("--source", default="")
    parser.add_argument("--media", help="Local approved source for offline preview/testing")
    parser.add_argument("--transcript", help="Optional reviewed timestamped JSON transcript")
    parser.add_argument("--clip")
    parser.add_argument("--run-id")
    parser.add_argument("--approved", action="store_true")
    parser.add_argument("--automatic", action="store_true")
    args = parser.parse_args()
    if args.command == "preview":
        preview(args)
    elif args.command == "verify-run":
        verify_run(args.run_id)
    else:
        publish(args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as exc:
        print(f"Clipping stopped: {exc}")
        raise SystemExit(1)
    except Exception as exc:
        # Third-party exceptions may contain signed URLs/tokens.
        print(f"Clipping stopped: {type(exc).__name__}. Check configuration and provider status.")
        raise SystemExit(1)
