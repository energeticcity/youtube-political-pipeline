#!/usr/bin/env python3
"""
Daily Dad Joke Pipeline
Fetches a clean dad joke, generates voiceover via ElevenLabs, animates a dad avatar
via HeyGen, renders intro/outro cards + captions, and publishes to YouTube + RSS feed
(which Publer reads to auto-post to TikTok and Instagram).
"""

import os
import re
import sys
import time
import json
import random
import base64
import requests
import tempfile
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
HEYGEN_API_KEY = os.environ["HEYGEN_API_KEY"]
HEYGEN_AVATAR_ID = os.environ["HEYGEN_AVATAR_ID"]

YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
YOUTUBE_CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "energeticcity/youtube-political-pipeline")

ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "EkK5I93UQWFDigLMpZcX")
GEMINI_MODEL = "gemini-2.0-flash"


def log(msg: str):
    print(f"[pipeline] {msg}", flush=True)


def extract_tag(text: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return m.group(1).strip() if m else ""


def call_llm(system: str, user_message: str, max_tokens: int = 512) -> str:
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        params={"key": GEMINI_API_KEY},
        headers={"content-type": "application/json"},
        json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.9,
            },
        },
        timeout=60,
    )
    if resp.status_code != 200:
        log(f"  Gemini API error {resp.status_code}: {resp.text[:500]}")
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


# ── Step 1: Fetch a dad joke ──────────────────────────────────────────────────

JOKE_BLOCKLIST = {
    "sex", "porn", "drug", "kill", "death", "fuck", "shit", "rape",
    "racist", "nazi", "suicide", "abortion", "gun", "shoot",
}


def split_joke(joke_text: str) -> tuple[str, str]:
    """Split a one-string joke into (setup, punchline) using heuristics."""
    text = joke_text.strip()
    # Q/A format: split on first '?'
    if "?" in text:
        idx = text.index("?") + 1
        setup = text[:idx].strip()
        punchline = text[idx:].strip()
        if setup and punchline and len(punchline) > 3:
            return setup, punchline
    # Statement/punchline: split on first '. '
    if ". " in text:
        first, rest = text.split(". ", 1)
        if len(rest.strip()) > 5:
            return first.strip() + ".", rest.strip()
    return text, ""


def fetch_dad_joke() -> dict:
    """Pull a clean joke from icanhazdadjoke.com; Gemini fallback if needed."""
    log("Fetching dad joke from icanhazdadjoke.com...")

    headers = {
        "Accept": "application/json",
        "User-Agent": "DadJokeFix (https://github.com/energeticcity/youtube-political-pipeline)",
    }

    for attempt in range(5):
        try:
            resp = requests.get(
                "https://icanhazdadjoke.com/",
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            joke_text = (resp.json().get("joke") or "").strip()

            if not joke_text or len(joke_text) > 280:
                continue
            if any(bad in joke_text.lower() for bad in JOKE_BLOCKLIST):
                continue

            setup, punchline = split_joke(joke_text)
            if setup and punchline:
                log(f"  Picked joke from icanhazdadjoke (attempt {attempt + 1})")
                return {"setup": setup, "punchline": punchline, "source": "icanhazdadjoke"}
        except Exception as e:
            log(f"  icanhazdadjoke attempt {attempt + 1} failed: {e}")

    log("  No cleanly-splittable joke found, falling back to Gemini")
    result = call_llm(
        system="You are a dad telling clean, family-friendly dad jokes. Output ONLY the requested format.",
        user_message="""Write one original dad joke. The setup should end with a question or "...". The punchline must be a groan-worthy pun. Keep both lines short.

Respond ONLY:
<SETUP>[the setup line, max 100 chars]</SETUP>
<PUNCHLINE>[the punchline, max 100 chars]</PUNCHLINE>""",
        max_tokens=200,
    )
    return {
        "setup": extract_tag(result, "SETUP"),
        "punchline": extract_tag(result, "PUNCHLINE"),
        "source": "gemini",
    }


# ── Step 2: Build the spoken script ───────────────────────────────────────────

CATCHPHRASES = [
    "Alright, dad joke incoming.",
    "You ready for this one?",
    "Got one for ya.",
    "Alright, here's one.",
    "Buckle up, this is a good one.",
    "Okay, hear me out.",
    "Joke o'clock, let's go.",
]


def write_script(joke: dict, episode: int) -> dict:
    """Construct the TTS script: catchphrase hook → setup → beat → punchline → CTA."""
    setup = joke["setup"].rstrip("?.!").strip()
    punchline = joke["punchline"].strip()
    catchphrase = random.choice(CATCHPHRASES)

    script = (
        f"{catchphrase}.. {setup}... ... ... {punchline}. "
        f"Two dad jokes every day, follow for more!"
    )
    return {
        "script": script,
        "setup": joke["setup"],
        "punchline": joke["punchline"],
        "catchphrase": catchphrase,
        "episode": episode,
    }


# ── Step 3: YouTube metadata ──────────────────────────────────────────────────

def generate_metadata(joke: dict, episode: int) -> dict:
    log("Generating YouTube metadata...")
    result = call_llm(
        system="You are a YouTube SEO writer for the channel 'Dad Joke Fix' — a daily dad joke channel. Output ONLY the requested XML format.",
        user_message=f"""Generate metadata for Dad Joke Fix episode #{episode}.

Setup: {joke['setup']}
Punchline: {joke['punchline']}

Rules:
- Title: MUST start with "Dad Joke #{episode}:". Then a short hook based on the setup. DO NOT spoil the punchline. Total under 60 chars.
- Description: include the joke text, then "Follow @dadjokefix for 2 dad jokes every day!", then 5 hashtags including #dadjokes #shorts #dadjokefix.
- Tags: dadjokes, dadjoke, dadjokefix, comedy, shorts, funny, jokes, family, plus 3 specific to this joke.
- Thumb text: 2-3 ALL CAPS words teasing the joke without spoiling.

Respond ONLY:
<TITLE>[under 60 chars]</TITLE>
<DESCRIPTION>[joke + cta + hashtags]</DESCRIPTION>
<TAGS>[comma-separated tags]</TAGS>
<THUMB>[2-3 ALL CAPS words]</THUMB>""",
        max_tokens=600,
    )
    return {
        "title": extract_tag(result, "TITLE"),
        "description": extract_tag(result, "DESCRIPTION"),
        "tags": extract_tag(result, "TAGS"),
        "thumb_text": extract_tag(result, "THUMB"),
    }


# ── Step 4: ElevenLabs TTS ────────────────────────────────────────────────────

def generate_tts(script: str) -> bytes:
    log("Generating TTS audio via ElevenLabs...")
    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
        params={"output_format": "mp3_44100_128"},
        headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "accept": "audio/mpeg",
        },
        json={
            "text": script,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.6,
                "similarity_boost": 0.75,
                "style": 0.15,
                "use_speaker_boost": False,
            },
        },
        timeout=120,
    )
    resp.raise_for_status()
    log(f"  Got {len(resp.content)} bytes of audio")
    return resp.content


def denoise_audio(input_path: str, output_path: str) -> str:
    """Apply FFT denoising + highpass + gentle compression to clean up TTS hiss."""
    import subprocess
    log("Denoising TTS audio...")
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", input_path,
            "-af", "afftdn=nf=-25:nr=12:nt=w,highpass=f=80,acompressor=threshold=-22dB:ratio=2:attack=20:release=200",
            "-ar", "44100",
            "-b:a", "192k",
            output_path,
        ],
        check=True,
    )
    return output_path


# ── Episode counter (stored in repo as state.json) ────────────────────────────

def get_and_increment_episode_count() -> int:
    """Read state.json from the repo, increment episode counter, push back. Returns new count."""
    if not GITHUB_TOKEN:
        log("Episode counter skipped (no GITHUB_TOKEN); using fallback 1")
        return 1

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    state_path = "state.json"

    resp = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/{state_path}",
        headers=headers, timeout=15,
    )

    existing_sha = None
    state = {"episode": 0}
    if resp.status_code == 200:
        existing_sha = resp.json()["sha"]
        try:
            state = json.loads(base64.b64decode(resp.json()["content"]).decode("utf-8"))
        except Exception:
            state = {"episode": 0}

    state["episode"] = int(state.get("episode", 0)) + 1
    new_count = state["episode"]
    log(f"  Episode #{new_count}")

    push_data = {
        "message": f"Bump episode counter to #{new_count}",
        "content": base64.b64encode(json.dumps(state, indent=2).encode()).decode(),
    }
    if existing_sha:
        push_data["sha"] = existing_sha

    put_resp = requests.put(
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/{state_path}",
        headers=headers, json=push_data, timeout=30,
    )
    put_resp.raise_for_status()
    return new_count


# ── Step 5: Host audio on GitHub Release for HeyGen to fetch ──────────────────

def upload_to_github_release(
    file_path: str, tag_name: str, filename: str, content_type: str
) -> str:
    """Upload any asset to a GitHub Release (creates the release if needed)."""
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN required to host assets")

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    release_data = {
        "tag_name": tag_name,
        "name": f"Dad Joke {tag_name}",
        "body": "Auto-generated dad joke video assets.",
        "draft": False,
        "prerelease": False,
    }
    resp = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/releases",
        headers=headers, json=release_data, timeout=30,
    )
    if resp.status_code not in (201, 422):
        resp.raise_for_status()

    if resp.status_code == 422:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{tag_name}",
            headers=headers, timeout=15,
        )
        resp.raise_for_status()

    release = resp.json()
    upload_url = release["upload_url"].replace("{?name,label}", "")

    with open(file_path, "rb") as f:
        data = f.read()

    log(f"  Uploading {filename} ({len(data) / 1024:.0f} KB) to release {tag_name}...")
    asset_resp = requests.post(
        f"{upload_url}?name={filename}",
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Content-Type": content_type,
        },
        data=data,
        timeout=300,
    )
    if asset_resp.status_code == 422:
        # Asset with this name already exists in the release; fetch its URL
        for asset in release.get("assets", []):
            if asset.get("name") == filename:
                return asset["browser_download_url"]
        asset_resp.raise_for_status()
    asset_resp.raise_for_status()
    return asset_resp.json()["browser_download_url"]


# ── Step 6: HeyGen avatar generation ──────────────────────────────────────────

def generate_avatar_video(audio_url: str, output_path: str) -> str:
    """Animate Hank lip-syncing to the given audio URL via HeyGen. Returns local MP4 path."""
    log("Generating talking dad avatar via HeyGen...")

    headers = {
        "X-Api-Key": HEYGEN_API_KEY,
        "Content-Type": "application/json",
    }

    create_resp = requests.post(
        "https://api.heygen.com/v2/video/generate",
        headers=headers,
        json={
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": HEYGEN_AVATAR_ID,
                        "avatar_style": "normal",
                    },
                    "voice": {
                        "type": "audio",
                        "audio_url": audio_url,
                    },
                }
            ],
            "dimension": {"width": 720, "height": 1280},
        },
        timeout=30,
    )
    if create_resp.status_code != 200:
        log(f"  HeyGen create error {create_resp.status_code}: {create_resp.text[:500]}")
    create_resp.raise_for_status()
    video_id = create_resp.json()["data"]["video_id"]
    log(f"  Video job created: {video_id}, polling for completion...")

    for attempt in range(80):  # up to ~6.5 minutes (HeyGen can be slow under load)
        time.sleep(5)
        status_resp = requests.get(
            "https://api.heygen.com/v1/video_status.get",
            params={"video_id": video_id},
            headers={"X-Api-Key": HEYGEN_API_KEY},
            timeout=15,
        )
        status_resp.raise_for_status()
        data = status_resp.json().get("data", {})
        status = data.get("status")

        if status == "completed":
            video_url = data["video_url"]
            log(f"  HeyGen render done, downloading {video_url[:80]}...")
            video_resp = requests.get(video_url, timeout=180)
            video_resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(video_resp.content)
            log(f"  Avatar saved: {output_path} ({len(video_resp.content) / 1024:.0f} KB)")
            return output_path
        if status == "failed":
            raise RuntimeError(f"HeyGen failed: {data.get('error') or data}")

        if attempt % 4 == 0:
            log(f"  HeyGen status: {status}")

    raise TimeoutError("HeyGen render timed out after 6.5 minutes")


# ── Step 7: YouTube upload ────────────────────────────────────────────────────

def get_youtube_access_token() -> str:
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": YOUTUBE_CLIENT_ID,
            "client_secret": YOUTUBE_CLIENT_SECRET,
            "refresh_token": YOUTUBE_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def upload_short_to_youtube(short_path: str, thumbnail_path: str, metadata: dict) -> str:
    if not YOUTUBE_REFRESH_TOKEN:
        log("YouTube upload skipped (no refresh token configured)")
        return ""

    log("Uploading dad joke Short to YouTube...")
    access_token = get_youtube_access_token()

    tags = [t.strip() for t in metadata["tags"].split(",") if t.strip()][:15]
    if "shorts" not in [t.lower() for t in tags]:
        tags.append("shorts")

    short_title = metadata["title"]
    if "#shorts" not in short_title.lower():
        short_title = f"{short_title} #Shorts"
    if len(short_title) > 100:
        short_title = short_title[:100]

    init_resp = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "snippet": {
                "title": short_title,
                "description": metadata["description"],
                "tags": tags,
                "categoryId": "23",  # Comedy
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        },
        timeout=30,
    )
    if init_resp.status_code != 200:
        log(f"  YouTube API error {init_resp.status_code}: {init_resp.text[:500]}")
    init_resp.raise_for_status()
    upload_url = init_resp.headers["Location"]

    with open(short_path, "rb") as f:
        video_data = f.read()

    log(f"  Uploading {len(video_data) / (1024 * 1024):.1f} MB...")
    upload_resp = requests.put(
        upload_url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "video/mp4",
            "Content-Length": str(len(video_data)),
        },
        data=video_data,
        timeout=600,
    )
    upload_resp.raise_for_status()
    short_id = upload_resp.json()["id"]
    log(f"  Uploaded: https://youtube.com/shorts/{short_id}")

    # Optional thumbnail upload
    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            with open(thumbnail_path, "rb") as f:
                thumb_data = f.read()
            thumb_resp = requests.post(
                "https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
                params={"videoId": short_id},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "image/jpeg",
                },
                data=thumb_data,
                timeout=60,
            )
            thumb_resp.raise_for_status()
            log("  Thumbnail set!")
        except Exception as e:
            log(f"  WARNING: Thumbnail upload failed: {e}")

    return short_id


# ── Step 8: RSS feed update (Publer reads this) ───────────────────────────────

def update_rss_feed(video_url: str, metadata: dict, joke: dict, youtube_short_id: str = ""):
    """Update feed.xml in the repo with the new dad joke entry. Publer auto-posts from this."""
    if not GITHUB_TOKEN:
        log("RSS feed update skipped (no GITHUB_TOKEN)")
        return

    from datetime import datetime, timezone
    import xml.etree.ElementTree as ET
    import base64

    log("Updating RSS feed...")
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    feed_path = "feed.xml"
    existing_sha = None
    existing_xml = None

    resp = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/{feed_path}",
        headers=headers, timeout=15,
    )
    if resp.status_code == 200:
        existing_sha = resp.json()["sha"]
        existing_xml = base64.b64decode(resp.json()["content"]).decode("utf-8")

    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    channel = None
    if existing_xml:
        try:
            root = ET.fromstring(existing_xml)
            channel = root.find("channel")
            # If the existing feed is from the political pipeline, rebuild it for dad jokes
            existing_title = channel.find("title").text if channel is not None and channel.find("title") is not None else ""
            if "Political" in existing_title:
                log("  Existing feed is political; rebuilding for dad jokes")
                channel = None
        except ET.ParseError:
            channel = None

    if channel is None:
        root = ET.Element("rss", version="2.0", attrib={
            "xmlns:media": "http://search.yahoo.com/mrss/",
            "xmlns:atom": "http://www.w3.org/2005/Atom",
        })
        channel = ET.SubElement(root, "channel")
        ET.SubElement(channel, "title").text = "Two Dad Jokes Daily"
        ET.SubElement(channel, "link").text = f"https://github.com/{GITHUB_REPO}"
        ET.SubElement(channel, "description").text = "Two fresh dad jokes every day, delivered by an animated dad. For TikTok and Instagram Reels."
        ET.SubElement(channel, "language").text = "en-us"

    last_build = channel.find("lastBuildDate")
    if last_build is None:
        last_build = ET.SubElement(channel, "lastBuildDate")
    last_build.text = now

    item = ET.Element("item")
    ET.SubElement(item, "title").text = metadata.get("title", "Dad Joke")

    desc_parts = [
        f"{joke['setup']}",
        "",
        f"{joke['punchline']}",
        "",
        "Follow for two dad jokes a day!",
    ]
    if video_url:
        desc_parts.append(f"\nVideo: {video_url}")
    if youtube_short_id:
        desc_parts.append(f"Watch: https://youtube.com/shorts/{youtube_short_id}")
    desc_parts.append("\n#dadjokes #dadjoke #comedy #shorts #funny")
    ET.SubElement(item, "description").text = "\n".join(desc_parts)

    if youtube_short_id:
        ET.SubElement(item, "link").text = f"https://youtube.com/shorts/{youtube_short_id}"
        ET.SubElement(item, "guid", isPermaLink="true").text = f"https://youtube.com/shorts/{youtube_short_id}"
    elif video_url:
        ET.SubElement(item, "link").text = video_url
        ET.SubElement(item, "guid", isPermaLink="false").text = video_url

    ET.SubElement(item, "pubDate").text = now

    # Enclosure tag — Make.com / RSS readers auto-extract the video URL from this
    if video_url:
        ET.SubElement(item, "enclosure", {
            "url": video_url,
            "type": "video/mp4",
            "length": "0",
        })

    items = channel.findall("item")
    if items:
        idx = list(channel).index(items[0])
        channel.insert(idx, item)
    else:
        channel.append(item)

    all_items = channel.findall("item")
    for old_item in all_items[20:]:
        channel.remove(old_item)

    ET.indent(root, space="  ")
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")

    push_data = {
        "message": f"Add dad joke: {metadata.get('title', 'new joke')}",
        "content": base64.b64encode(xml_str.encode()).decode(),
    }
    if existing_sha:
        push_data["sha"] = existing_sha

    resp = requests.put(
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/{feed_path}",
        headers=headers, json=push_data, timeout=30,
    )
    resp.raise_for_status()
    log(f"  RSS feed updated: https://raw.githubusercontent.com/{GITHUB_REPO}/main/feed.xml")


# ── TikTok manual-upload notification ─────────────────────────────────────────

def notify_for_tiktok(video_url: str, joke: dict, metadata: dict, episode: int):
    """Create a GitHub Issue with the video link + ready-to-paste TikTok caption.
    GitHub emails the issue automatically — open on phone, download, upload to TikTok."""
    if not GITHUB_TOKEN:
        log("TikTok notification skipped (no GITHUB_TOKEN)")
        return

    log("Posting TikTok manual-upload notification...")
    try:
        caption = (
            f"{joke['setup']} {joke['punchline']} "
            f"#dadjokes #dadjoke #dadjokefix #comedy #fyp #foryou #funny #jokes"
        )
        body = (
            f"## Dad Joke #{episode} — ready for TikTok\n\n"
            f"**[📱 Download video on phone]({video_url})**\n\n"
            f"### TikTok caption (tap to copy)\n"
            f"```\n{caption}\n```\n\n"
            f"### Setup\n{joke['setup']}\n\n"
            f"### Punchline\n{joke['punchline']}\n\n"
            f"### Suggested workflow\n"
            f"1. Tap the download link above on your phone\n"
            f"2. Save the video to your camera roll\n"
            f"3. Open TikTok → + → upload from camera roll\n"
            f"4. Tap **Add sound** and pick a trending audio (lower its volume)\n"
            f"5. Paste the caption above and post\n"
        )

        resp = requests.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/issues",
            headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
            },
            json={
                "title": f"📱 TikTok upload ready: Dad Joke #{episode}",
                "body": body,
                "labels": ["tiktok-upload"],
            },
            timeout=30,
        )
        resp.raise_for_status()
        log(f"  Issue created: {resp.json().get('html_url', '')}")
    except Exception as e:
        log(f"  WARNING: TikTok notification failed: {e}")


# ── Main pipeline ─────────────────────────────────────────────────────────────

def main():
    log("=" * 60)
    log("Daily Dad Joke Pipeline")
    log("=" * 60)

    output_dir = tempfile.mkdtemp(prefix="dadjoke_")
    log(f"Output dir: {output_dir}")

    from datetime import datetime, timezone
    tag = datetime.now(timezone.utc).strftime("v%Y%m%d-%H%M")

    # 1. Joke
    joke = fetch_dad_joke()
    if not joke.get("setup") or not joke.get("punchline"):
        raise RuntimeError(f"Failed to get a usable joke: {joke}")
    log(f"  Setup:     {joke['setup']}")
    log(f"  Punchline: {joke['punchline']}")

    # 2. Episode counter
    episode = get_and_increment_episode_count()

    # 3. Script
    script_data = write_script(joke, episode)
    log(f"  Script ({len(script_data['script'])} chars): {script_data['script']}")

    # 4. Metadata
    metadata = generate_metadata(joke, episode)
    log(f"  Title: {metadata['title']}")

    # 4. TTS
    audio_data = generate_tts(script_data["script"])
    raw_audio_path = os.path.join(output_dir, "voiceover_raw.mp3")
    with open(raw_audio_path, "wb") as f:
        f.write(audio_data)

    # 4b. Denoise the TTS output before HeyGen fetches it
    audio_path = os.path.join(output_dir, "voiceover.mp3")
    denoise_audio(raw_audio_path, audio_path)

    # 5. Host audio so HeyGen can fetch it
    audio_url = upload_to_github_release(
        audio_path, tag, f"audio_{tag}.mp3", "audio/mpeg"
    )

    # 6. HeyGen avatar
    avatar_path = os.path.join(output_dir, "avatar.mp4")
    generate_avatar_video(audio_url, avatar_path)

    # 7. Render final Short with intro/outro/captions
    from dad_video_renderer import render_dad_short, render_thumbnail
    short_path = os.path.join(output_dir, "dad_short.mp4")
    render_dad_short(
        avatar_path=avatar_path,
        joke=joke,
        episode=episode,
        catchphrase=script_data["catchphrase"],
        output_path=short_path,
    )

    thumb_path = os.path.join(output_dir, "thumbnail.jpg")
    render_thumbnail(
        thumb_text=metadata["thumb_text"],
        joke=joke,
        episode=episode,
        output_path=thumb_path,
    )

    # 8. Upload to YouTube as a Short
    short_id = ""
    try:
        short_id = upload_short_to_youtube(short_path, thumb_path, metadata)
    except Exception as e:
        log(f"  WARNING: YouTube upload failed: {e}")

    # 9. Upload final video to GitHub Release + update RSS for Make.com (IG)
    video_url = ""
    try:
        video_url = upload_to_github_release(
            short_path, tag, f"short_{tag}.mp4", "video/mp4"
        )
        update_rss_feed(
            video_url=video_url,
            metadata=metadata,
            joke=joke,
            youtube_short_id=short_id,
        )
    except Exception as e:
        log(f"  WARNING: GitHub Release / RSS update failed: {e}")

    # 10. TikTok manual-upload notification
    if video_url:
        notify_for_tiktok(video_url, joke, metadata, episode)

    log("=" * 60)
    log("Pipeline complete!")
    log("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"PIPELINE FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
