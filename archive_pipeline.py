#!/usr/bin/env python3
"""Curated archival stories: source verification, original narration, previews, gated delivery."""
import argparse
import base64
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote

import requests
import clipping as clips

CATALOG = Path(__file__).parent / "archives/episodes.json"


def catalog(path=CATALOG):
    data = json.loads(Path(path).read_text())
    if data.get("version") != 1:
        raise ValueError("Unsupported archive catalogue")
    sources = {s["id"]: s for s in data["sources"]}
    if len(sources) != len(data["sources"]):
        raise ValueError("Duplicate sources")
    seen = set()
    for s in sources.values():
        clips.identifier(s["id"])
        clips.identifier(s["archive_id"])
        if not re.fullmatch(r"[A-Za-z0-9_.-]+\.mp4", s["filename"]):
            raise ValueError("Invalid archive filename")
        if s["license_url"] != "http://creativecommons.org/licenses/publicdomain/":
            raise ValueError("Unreviewed licence")
        if not re.fullmatch(r"[a-f0-9]{64}", s["sha256"]):
            raise ValueError("Missing source fingerprint")
        if not s.get("rights_note") or not s.get("rights_checked"):
            raise ValueError("Missing rights evidence")
    for e in data["episodes"]:
        clips.identifier(e["id"])
        if e["id"] in seen or e["source_id"] not in sources:
            raise ValueError("Duplicate episode or unknown source")
        seen.add(e["id"])
        if not isinstance(e.get("auto_publish_approved"), bool):
            raise ValueError("Explicit publication setting required")
        if not 1 <= len(e["beats"]) <= 10 or not 1 <= len(e["title"]) <= 100:
            raise ValueError("Invalid episode")
        for b in e["beats"]:
            if not isinstance(b["start"], (int, float)) or not math.isfinite(b["start"]) or b["start"] < 0:
                raise ValueError("Invalid shot start")
            if not isinstance(b["text"], str) or not b["text"].strip():
                raise ValueError("Empty narration")
        if not 50 <= len(script(e).split()) <= 150:
            raise ValueError("Narration must be 50–150 words")
    return data, sources


def script(episode):
    return " ".join(b["text"] for b in episode["beats"])


def check_rights(source):
    response = requests.get(f"https://archive.org/metadata/{source['archive_id']}", timeout=60)
    response.raise_for_status()
    data = response.json()
    metadata = data.get("metadata", {})
    collections = metadata.get("collection", [])
    if isinstance(collections, str):
        collections = [collections]
    if (metadata.get("identifier") != source["archive_id"] or "prelinger" not in collections
            or metadata.get("licenseurl") != source["license_url"]
            or not any(f["name"] == source["filename"] for f in data.get("files", []))):
        raise ValueError("Archive rights or source changed; editorial review required")
    return {k: metadata.get(k) for k in ("identifier", "title", "creator", "date", "licenseurl", "collection", "description")}


def narration(episode, directory):
    voice = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key or not voice:
        raise ValueError("Existing ElevenLabs key and voice ID are required")
    clips.identifier(voice)
    text = script(episode)
    response = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps",
        headers={"xi-api-key": key}, params={"output_format": "mp3_44100_128"},
        json={"text": text, "model_id": "eleven_multilingual_v2",
              "voice_settings": {"stability": 0.45, "similarity_boost": 0.75}}, timeout=180)
    if not response.ok:
        raise RuntimeError(f"Narration HTTP {response.status_code}; no video published")
    data = response.json()
    alignment = data.get("alignment")
    if not alignment or "".join(alignment["characters"]) != text:
        raise ValueError("Narration alignment differs from approved script")
    starts, ends = alignment["character_start_times_seconds"], alignment["character_end_times_seconds"]
    if len(starts) != len(text) or len(ends) != len(text):
        raise ValueError("Invalid narration alignment")
    for i, (start, end) in enumerate(zip(starts, ends)):
        if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start <= end or (i and start < starts[i-1]):
            raise ValueError("Nonmonotonic narration timestamps")
    audio = directory / "narration.mp3"
    audio.write_bytes(base64.b64decode(data["audio_base64"], validate=True))
    duration = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(audio)]))
    if not math.isfinite(duration) or not 20 <= duration <= 60 or ends[-1] > duration + 0.1:
        raise ValueError("Narration outside 20–60 second limit")
    # Word-aligned groups, preserving actual TTS pauses (not estimated speech timing).
    segments = []
    words = list(re.finditer(r"\S+", text))
    for i in range(0, len(words), 6):
        group = words[i:i+6]
        segments.append({"start": starts[group[0].start()], "end": ends[group[-1].end()-1],
                         "text": text[group[0].start():group[-1].end()]})
    boundaries, offset = [], 0
    for b in episode["beats"]:
        boundaries.append(starts[offset])
        offset += len(b["text"]) + 1
    boundaries[0] = 0
    boundaries.append(duration)
    return audio, duration, segments, boundaries


def render(source_file, episode, source, directory, audio, duration, segments, boundaries):
    _, source_duration = clips.probe(source_file)
    clips.captions({"start": 0, "segments": segments}, directory / "captions.ass")
    with open(directory / "captions.ass", "a") as f:
        end = clips.ass_time(duration)
        lines = [(r"{\an8\pos(540,155)\fs34\c&H60D6FF&}", "THE PAST WAS RIDICULOUS"),
                 (r"{\an8\pos(540,270)\fs62}", episode["headline"]),
                 (r"{\an8\pos(540,1720)\fs27}", "ARCHIVAL FILM • 1956 | ORIGINAL COMMENTARY"),
                 (r"{\an8\pos(540,1770)\fs23}", "MPO Productions / Prelinger Archives")]
        for style, text in lines:
            text = r"\N".join(clips.safe_ass(line) for line in text.splitlines())
            f.write(f"Dialogue: 1,0:00:00.00,{end},Default,,0,0,0,,{style}{text}\n")
    shutil.copytree(clips.ROOT / "fonts", directory / "fonts", dirs_exist_ok=True)
    shot_files = []
    for i, beat in enumerate(episode["beats"]):
        length = boundaries[i+1] - boundaries[i]
        if length <= 0 or beat["start"] + length > source_duration:
            raise ValueError("Shot exceeds source bounds")
        name = f"shot-{i}.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(beat["start"]),
            "-i", str(Path(source_file).resolve()), "-t", str(length), "-an",
            "-vf", "scale=1080:900:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=1080:1920:(ow-iw)/2:520:color=0x101826,setsar=1",
            "-r", "30", "-c:v", "libx264", "-preset", "fast", "-crf", "21", "-pix_fmt", "yuv420p", name],
            cwd=directory, check=True, timeout=300)
        shot_files.append(f"file '{name}'")
    (directory / "shots.txt").write_text("\n".join(shot_files))
    output = directory / "clip.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "1",
        "-i", "shots.txt", "-i", str(audio.resolve()), "-map", "0:v:0", "-map", "1:a:0", "-t", str(duration),
        "-vf", "ass=captions.ass:fontsdir=fonts", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:v", "libx264", "-preset", "fast", "-crf", "21", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(output.resolve())],
        cwd=directory, check=True, timeout=600)
    info, actual = clips.probe(output)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    if (video["width"], video["height"]) != (1080, 1920) or abs(actual-duration) > 0.3:
        raise ValueError("Output verification failed")
    return output


def publication_source(episode, source):
    return {"id": source["id"], "enabled": episode["enabled"], "rights_confirmed": True, "editing_allowed": True,
        "rights_type": "public_domain_archive", "license_url": source["license_url"], "creator": source["creator"],
        "campaign_url": source["url"], "permission_reference": source["url"], "rules": source["rights_note"],
        "attribution": source["title"] + " — " + source["creator"] + " / Prelinger Archives. " + source["url"],
        "sha256": source["sha256"], "platforms": ["youtube", "instagram", "tiktok"], "made_for_kids": False,
        "branded_content": False, "synthetic_narration": True, "auto_publish_approved": episode["auto_publish_approved"],
        "episode_digest": clips.digest(episode)}


def previewed(episode_id):
    page = 1
    while True:
        issues = clips.github("GET", "issues", params={"state": "all", "per_page": 100, "page": page})
        if any(i["title"] == f"[archive-preview] {episode_id}" for i in issues):
            return True
        if len(issues) < 100:
            return False
        page += 1


def preview(args):
    data, sources = catalog(args.catalog)
    episodes = [e for e in data["episodes"] if e.get("enabled") and (not args.episode or e["id"] == args.episode)]
    if args.episode and not episodes:
        raise ValueError("Unknown/disabled episode")
    if not args.episode and os.environ.get("GH_TOKEN"):
        episodes = [e for e in episodes if not previewed(e["id"]) and not clips.reserved(e["id"])]
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"version": 1, "commit": os.environ.get("GITHUB_SHA", "local"), "catalog_digest": clips.digest(data), "clips": []}
    for episode in episodes[:1]:
        source = sources[episode["source_id"]]
        evidence = check_rights(source)
        with tempfile.TemporaryDirectory(prefix="archive-story-") as scratch:
            directory = Path(scratch)
            media = Path(args.media).resolve() if args.media else directory / "source.mp4"
            if not args.media:
                clips.download(f"https://archive.org/download/{source['archive_id']}/{quote(source['filename'])}", media)
            if clips.file_hash(media) != source["sha256"]:
                raise ValueError("Archive source fingerprint changed")
            audio, duration, segments, boundaries = narration(episode, directory)
            video = render(media, episode, source, directory, audio, duration, segments, boundaries)
            dest = out / episode["id"]
            dest.mkdir(exist_ok=True)
            for name in ("clip.mp4", "captions.ass", "narration.mp3"):
                shutil.copy(directory / name, dest / name)
            (dest / "script.txt").write_text(script(episode) + "\n")
            (dest / "rights.json").write_text(json.dumps({"catalogue": source, "live_metadata": evidence}, indent=2))
            pub = publication_source(episode, source)
            caption = episode["title"] + "\n\nOriginal historical commentary. Archival promotional fantasy, not a current product.\n" + pub["attribution"] + "\nNarration generated with AI. #History #RetroFuture"
            manifest["clips"].append({"id": episode["id"], "source_id": source["id"], "source_digest": clips.digest(pub),
                "sha256": clips.file_hash(video), "title": episode["title"], "caption": caption, "duration": duration})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    summary = "# The Past Was Ridiculous\n\n" + ("Preview ready. Check footage, narration, captions and rights before publication.\n" if manifest["clips"] else "Queue exhausted. Add reviewed stories; no narration purchased or video posted.\n")
    (out / "REVIEW.md").write_text(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(summary)
    print(summary)


def publish(args):
    if os.environ.get("CLIP_PUBLISH_ENABLED") != "true" or not args.approved:
        raise ValueError("Publishing remains disabled until preview approval")
    if args.automatic and os.environ.get("CLIP_AUTO_PUBLISH_ENABLED") != "true":
        raise ValueError("Automatic publication disabled")
    run = clips.verify_run(args.run_id)
    data, sources = catalog(args.catalog)
    manifest = json.loads((Path(args.output) / "manifest.json").read_text())
    if manifest.get("version") != 1 or manifest["commit"] != run["head_sha"] or manifest["catalog_digest"] != clips.digest(data):
        raise ValueError("Preview provenance/catalogue mismatch; regenerate preview")
    for clip in manifest["clips"]:
        if args.episode and clip["id"] != args.episode:
            continue
        episode = next(e for e in data["episodes"] if e["id"] == clip["id"])
        if args.automatic and not episode["auto_publish_approved"]:
            continue
        check_rights(sources[episode["source_id"]])
        clips.publish_one(args, clip, publication_source(episode, sources[episode["source_id"]]))


def delivery(args):
    """Read provider results without exposing account tokens or raw diagnostic payloads."""
    clips.identifier(args.post_id)
    accounts = json.loads(os.environ['CLIP_DESTINATIONS_JSON'])
    data = clips.api_json('GET', 'https://api.postforme.dev/v1/social-post-results',
        os.environ['POSTFORME_API_KEY'], params={'post_id': args.post_id, 'limit': 100})
    rows = data if isinstance(data, list) else data.get('data', [])
    result = {}
    for platform, account in accounts.items():
        matches = [r for r in rows if r.get('post_id') == args.post_id and r.get('social_account_id') == account]
        successes = [r for r in matches if r.get('success') is True]
        if successes:
            url = (successes[-1].get('platform_data') or {}).get('url')
            result[platform] = {'status': 'published', 'url': url}
        elif matches:
            result[platform] = {'status': 'failed', 'result_id': matches[-1].get('id'),
                                'note': 'Inspect provider diagnostics; do not blindly retry the batch.'}
        else:
            result[platform] = {'status': 'pending'}
    print(json.dumps(result, indent=2))
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'delivery.json').write_text(json.dumps(result, indent=2))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
            f.write('## Archive delivery\n\n' + '\n'.join(f"- {p}: {r['status']}" for p, r in result.items()) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["preview", "publish", "mark-preview", "check", "accounts", "delivery"])
    p.add_argument("--catalog", default=str(CATALOG))
    p.add_argument("--episode", default="")
    p.add_argument("--output", default="clip-output")
    p.add_argument("--media")
    p.add_argument("--run-id")
    p.add_argument("--post-id")
    p.add_argument("--approved", action="store_true")
    p.add_argument("--automatic", action="store_true")
    args = p.parse_args()
    if args.command == "delivery":
        delivery(args)
    elif args.command == "accounts":
        accounts = []
        for offset in range(0, 1000, 50):
            payload = clips.api_json("GET", "https://api.postforme.dev/v1/social-accounts",
                os.environ["POSTFORME_API_KEY"], params={"limit": 50, "offset": offset})
            rows = payload if isinstance(payload, list) else payload.get("data", [])
            # The provider includes access/refresh tokens. Never serialize or log whole responses.
            accounts.extend({k: row.get(k) for k in ("id", "platform", "username", "user_id", "status")} for row in rows)
            if len(rows) < 50:
                break
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "destinations-review.json").write_text(json.dumps(accounts, indent=2))
        print(f"Saved {len(accounts)} account identities for destination review; credentials excluded.")
    elif args.command == "check":
        data, _ = catalog(args.catalog)
        print(f"Valid catalogue: {len(data['episodes'])} stories")
    elif args.command == "mark-preview":
        manifest = json.loads((Path(args.output) / "manifest.json").read_text())
        for clip in manifest["clips"]:
            if not previewed(clip["id"]):
                clips.github("POST", "issues", json={"title": f"[archive-preview] {clip['id']}",
                    "body": f"Preview artifact ready in Actions run {os.environ['GITHUB_RUN_ID']}. Not published.\nClosing this issue does not reset the queue. To regenerate, dispatch with this episode ID."})
    elif args.command == "preview":
        preview(args)
    else:
        publish(args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as error:
        raise SystemExit(str(error))
    except Exception as error:
        raise SystemExit(f"Archive pipeline stopped: {type(error).__name__}; no automatic retry of publication.")
