#!/usr/bin/env python3
"""
YouTube Political Channel Daily Pipeline
Fetches trending political news, generates a video script, renders it, and uploads to YouTube.
"""

import os
import re
import sys
import json
import requests
import tempfile
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
YOUTUBE_CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "UCWlSqBKvWmBcdLSPo7WL3PA")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

ELEVENLABS_VOICE_ID = "EkK5I93UQWFDigLMpZcX"

CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Pexels search terms by category — used to find relevant stock footage
PEXELS_SEARCH_TERMS = {
    "congress": "government building capitol",
    "economy": "stock market finance city",
    "military": "military defense national security",
    "election": "voting election democracy",
    "justice": "courthouse law legal scales",
    "international": "world globe diplomacy flags",
    "default": "american flag washington politics",
}


def fetch_pexels_backgrounds(category: str, topic: str, count: int = 3) -> list[str]:
    """Search Pexels for topic-relevant stock video. Returns list of video URLs."""
    if not PEXELS_API_KEY:
        log("  WARNING: No PEXELS_API_KEY set, using fallback dark background")
        return []

    # Try topic-specific search first, fall back to category keywords
    search_queries = [
        topic.split(":")[0][:40],  # First part of topic headline
        PEXELS_SEARCH_TERMS.get(category, PEXELS_SEARCH_TERMS["default"]),
    ]

    videos = []
    for query in search_queries:
        if len(videos) >= count:
            break
        try:
            log(f"  Searching Pexels: '{query}'...")
            resp = requests.get(
                "https://api.pexels.com/videos/search",
                params={
                    "query": query,
                    "per_page": 10,
                    "orientation": "landscape",
                    "size": "medium",
                },
                headers={"Authorization": PEXELS_API_KEY},
                timeout=15,
            )
            resp.raise_for_status()
            results = resp.json().get("videos", [])

            for vid in results:
                if len(videos) >= count:
                    break
                # Pick the HD file (720p or closest)
                files = sorted(
                    vid.get("video_files", []),
                    key=lambda f: abs(f.get("height", 0) - 720),
                )
                for vf in files:
                    if vf.get("width", 0) >= 1280 and vf.get("file_type") == "video/mp4":
                        videos.append(vf["link"])
                        log(f"  Found: {vf.get('width')}x{vf.get('height')} ({vid.get('duration', '?')}s)")
                        break
        except Exception as e:
            log(f"  Pexels search failed for '{query}': {e}")

    log(f"  Got {len(videos)} background videos from Pexels")
    return videos


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_tag(text: str, tag: str) -> str:
    """Extract content between XML-style tags."""
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return m.group(1).strip() if m else ""


def call_claude(system: str, user_message: str, max_tokens: int = 512) -> str:
    """Call the Anthropic Messages API and return the text response."""
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": CLAUDE_MODEL,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user_message}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"]


def log(msg: str):
    print(f"[pipeline] {msg}", flush=True)


# ── Step 1: Fetch Google News RSS ─────────────────────────────────────────────

def fetch_rss() -> str:
    log("Fetching Google News RSS...")
    resp = requests.get(
        "https://news.google.com/rss/search",
        params={"q": "US politics congress senate president white house", "hl": "en-US", "gl": "US", "ceid": "US:en"},
        headers={"User-Agent": "Mozilla/5.0 (compatible; RSS reader)"},
        timeout=30,
    )
    resp.raise_for_status()
    # Truncate to first 4000 chars for the prompt
    text = resp.text[:4000]
    log(f"  Got {len(resp.text)} bytes of RSS data")
    return text


# ── Step 2: Pick a topic ──────────────────────────────────────────────────────

def pick_topic(rss_text: str) -> dict:
    log("Asking Claude to pick a topic...")
    result = call_claude(
        system="You are a YouTube political topic selector. Respond ONLY with the exact XML format. No other text.",
        user_message=f"""Here are TODAY's top political news headlines from Google News:

{rss_text}

---
From these REAL headlines, select the single most YouTube-worthy political story. Pick something that is BREAKING or TRENDING right now — a specific bill, vote, scandal, conflict, or announcement that viewers will be searching for TODAY. Do NOT pick generic evergreen topics. Pick from the actual headlines above.

Also assign a background video category:
- congress: Senate, House, legislation, bills, congressional hearings
- economy: debt, inflation, GDP, spending, markets, taxes, budget
- military: defense, war, troops, weapons, veterans, national security
- election: campaigns, primaries, voting, polls, candidates
- justice: courts, crime, law enforcement, Supreme Court, legal
- international: foreign policy, diplomacy, trade deals, allies, UN
- default: use for immigration, healthcare, energy, or any other topic

Respond ONLY:
<TOPIC>specific headline/topic from the news above</TOPIC>
<ANGLE>your unique take or angle on this story</ANGLE>
<BGCATEGORY>one of: congress|economy|military|election|justice|international|default</BGCATEGORY>""",
    )
    topic = extract_tag(result, "TOPIC")
    angle = extract_tag(result, "ANGLE")
    bgcat = extract_tag(result, "BGCATEGORY").lower()
    if bgcat not in PEXELS_SEARCH_TERMS:
        bgcat = "default"
    log(f"  Topic: {topic}")
    log(f"  Angle: {angle}")
    log(f"  Category: {bgcat}")
    return {"topic": topic, "angle": angle, "bgcategory": bgcat}


# ── Step 3: Write script ──────────────────────────────────────────────────────

def write_script(topic_data: dict) -> dict:
    log("Asking Claude to write a script...")
    result = call_claude(
        system="You are a YouTube political content creator writing scripts for text-to-speech voiceover. Your scripts must sound completely natural when spoken aloud. Output ONLY the exact format requested. No extra commentary.",
        user_message=f"""Write a 300-400 word YouTube script for spoken delivery on this topic.
Topic: {topic_data['topic']}.
Angle: {topic_data['angle']}.

CRITICAL - This script will be read by a text-to-speech voice. Write it EXACTLY as someone would speak it out loud:
- Use short punchy sentences. Ten words max each.
- Use natural contractions: it's, don't, can't, we're, they've, that's
- Speak directly to the viewer using 'you' often
- Vary the rhythm - mix short bursts with slightly longer sentences
- Use casual connecting words: Look, Here's the thing, Now, But, And
- NO formal language. NO complex sentences. NO academic phrasing.
- Hook must grab in the first 5 words
- Add a dramatic pause with '...' where emphasis matters
- End with an urgent conversational call-to-action

Also write 4 key on-screen talking points (each max 8 words, punchy fact or claim).

Respond ONLY in this exact format with no other text:
<SCRIPT>
[your full spoken script]
</SCRIPT>
<POINT1>[talking point 1 - max 8 words]</POINT1>
<POINT2>[talking point 2 - max 8 words]</POINT2>
<POINT3>[talking point 3 - max 8 words]</POINT3>
<POINT4>[talking point 4 - max 8 words]</POINT4>""",
        max_tokens=2048,
    )
    return {
        "script": extract_tag(result, "SCRIPT"),
        "point1": extract_tag(result, "POINT1"),
        "point2": extract_tag(result, "POINT2"),
        "point3": extract_tag(result, "POINT3"),
        "point4": extract_tag(result, "POINT4"),
    }


# ── Step 4: Generate YouTube metadata ─────────────────────────────────────────

def generate_metadata(topic_data: dict, script_excerpt: str) -> dict:
    log("Asking Claude for YouTube metadata...")
    result = call_claude(
        system="You are a YouTube SEO expert for a political news channel called The Political Lens. Generate metadata optimized for TODAY's trending searches. Respond ONLY in the exact XML format. No other text.",
        user_message=f"""Generate YouTube metadata for this TIMELY political news video.
Topic: {topic_data['topic']}
Angle: {topic_data['angle']}
Script excerpt: {script_excerpt[:400]}

SEO RULES FOR TIMELY CONTENT:
- Title MUST include the specific person, place, bill, or event name
- Title should feel like it was written TODAY about a specific thing
- Primary keyword in the FIRST 30 characters of the title
- Tags MUST mix: (a) specific names/events, (b) broad political searches, (c) 'explained' / 'what happened' / 'breaking' variants
- Include the year 2026 in tags for recency signals
- First tag must be exact target keyword

DESCRIPTION MUST INCLUDE (in order):
1. A compelling 2-sentence hook at the very top
2. "In today's analysis:" followed by 4 bullet points (key talking points)
3. Timestamps: 0:00 Intro, 0:15 Point 1, etc.
4. Call to action: Subscribe + bell notification reminder
5. This EXACT disclosure at the end: "This video uses AI-assisted voiceover and script writing. All topics and editorial direction are selected by The Political Lens team."
6. 3-5 hashtags (#politics #news #[topic-specific])

Output ONLY in this exact format:
<YTITLE>[Specific, click-worthy title 50-60 chars]</YTITLE>
<YDESCRIPTION>[Full YouTube description with all elements above]</YDESCRIPTION>
<YTAGS>[15-20 comma-separated tags, max 500 chars total]</YTAGS>
<YTHUMB>[EXACTLY 2-3 ALL CAPS words for thumbnail text]</YTHUMB>""",
        max_tokens=1200,
    )
    return {
        "title": extract_tag(result, "YTITLE"),
        "description": extract_tag(result, "YDESCRIPTION"),
        "tags": extract_tag(result, "YTAGS"),
        "thumb_text": extract_tag(result, "YTHUMB"),
    }


# ── Step 5: ElevenLabs TTS ────────────────────────────────────────────────────

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
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.4,
                "similarity_boost": 0.8,
                "style": 0.3,
                "use_speaker_boost": True,
            },
        },
        timeout=120,
    )
    resp.raise_for_status()
    log(f"  Got {len(resp.content)} bytes of audio")
    return resp.content




# ── Step 7: Render video locally with FFmpeg ─────────────────────────────────

def render_video_local(audio_path: str, topic_data: dict, script_data: dict, output_dir: str) -> str:
    """Render video using the custom Pillow + FFmpeg renderer."""
    from video_renderer import render_video as _render_video

    log("Rendering video locally with FFmpeg...")
    bgcat = topic_data["bgcategory"]

    # Fetch background videos from Pexels based on topic
    bg_videos = fetch_pexels_backgrounds(bgcat, topic_data["topic"])

    talking_points = [
        script_data["point1"],
        script_data["point2"],
        script_data["point3"],
        script_data["point4"],
    ]

    video_path = os.path.join(output_dir, "output_video.mp4")
    _render_video(
        headline=topic_data["topic"],
        talking_points=talking_points,
        category=bgcat,
        bg_video_urls=bg_videos,
        audio_path=audio_path,
        output_path=video_path,
    )
    log(f"  Video rendered: {video_path}")
    return video_path


# ── Step 8: Render thumbnail locally with Pillow ─────────────────────────────

def render_thumbnail_local(topic_data: dict, metadata: dict, output_dir: str) -> str:
    """Render thumbnail using the custom Pillow renderer."""
    from video_renderer import render_thumbnail as _render_thumbnail

    log("Rendering thumbnail locally with Pillow...")
    thumb_path = os.path.join(output_dir, "thumbnail.jpg")
    _render_thumbnail(
        thumb_text=metadata["thumb_text"],
        category=topic_data["bgcategory"],
        output_path=thumb_path,
    )
    log(f"  Thumbnail rendered: {thumb_path}")
    return thumb_path


# ── Step 9: Render YouTube Short ───────────────────────────────────────────────

def render_short(video_path: str, audio_path: str, topic_data: dict, script_data: dict, output_dir: str) -> str:
    """Create a 9:16 vertical Short from the same content, max 60 seconds."""
    from video_renderer import render_short as _render_short

    log("Rendering YouTube Short (9:16 vertical)...")
    short_path = os.path.join(output_dir, "short_video.mp4")

    bgcat = topic_data["bgcategory"]
    bg_videos = fetch_pexels_backgrounds(bgcat, topic_data["topic"], count=1)

    talking_points = [
        script_data["point1"],
        script_data["point2"],
    ]

    _render_short(
        headline=topic_data["topic"],
        talking_points=talking_points,
        category=bgcat,
        bg_video_urls=bg_videos,
        audio_path=audio_path,
        output_path=short_path,
    )
    log(f"  Short rendered: {short_path}")
    return short_path


# ── Step 10: Upload to YouTube ─────────────────────────────────────────────────

def get_youtube_access_token() -> str:
    """Exchange refresh token for a fresh access token."""
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


def upload_to_youtube(video_path: str, thumbnail_path: str, metadata: dict):
    if not YOUTUBE_REFRESH_TOKEN:
        log("YouTube upload skipped (no refresh token configured)")
        log(f"  Video: {video_path}")
        log(f"  Thumbnail: {thumbnail_path}")
        log(f"  Title: {metadata['title']}")
        return

    log("Uploading to YouTube...")
    access_token = get_youtube_access_token()

    # Parse tags
    tags = [t.strip() for t in metadata["tags"].split(",") if t.strip()][:15]

    # Upload video using resumable upload
    log("  Starting YouTube resumable upload...")
    init_resp = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "snippet": {
                "title": metadata["title"],
                "description": metadata["description"],
                "tags": tags,
                "categoryId": "25",  # News & Politics
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        },
        timeout=30,
    )
    init_resp.raise_for_status()
    upload_url = init_resp.headers["Location"]

    # Upload the actual video data
    with open(video_path, "rb") as f:
        video_data = f.read()

    log(f"  Uploading {len(video_data) / (1024*1024):.1f} MB video...")
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
    video_id = upload_resp.json()["id"]
    log(f"  Video uploaded: https://youtube.com/watch?v={video_id}")

    # Set thumbnail (requires verified channel; skip gracefully if forbidden)
    log("  Setting thumbnail...")
    try:
        with open(thumbnail_path, "rb") as f:
            thumb_data = f.read()

        thumb_resp = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
            params={"videoId": video_id},
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
        log(f"  WARNING: Thumbnail upload failed (channel may need verification): {e}")
        log("  Video was uploaded successfully — thumbnail can be set manually.")
    log(f"  Done! https://youtube.com/watch?v={video_id}")
    return video_id


def upload_short_to_youtube(short_path: str, metadata: dict):
    """Upload a YouTube Short (vertical video, ≤60s)."""
    if not YOUTUBE_REFRESH_TOKEN:
        log("YouTube Short upload skipped (no refresh token)")
        return

    if not os.path.exists(short_path):
        log("YouTube Short upload skipped (no short video found)")
        return

    log("Uploading YouTube Short...")
    access_token = get_youtube_access_token()

    tags = [t.strip() for t in metadata["tags"].split(",") if t.strip()][:15]
    tags.append("shorts")

    # Shorts title: prepend #Shorts for discoverability
    short_title = metadata["title"]
    if len(short_title) > 90:
        short_title = short_title[:87] + "..."
    short_title = short_title + " #Shorts"
    if len(short_title) > 100:
        short_title = short_title[:100]

    short_desc = (
        f"{metadata['title']}\n\n"
        f"Watch the full analysis on our channel!\n\n"
        f"#politics #news #shorts #politicalnews\n\n"
        f"AI-generated political analysis. Not affiliated with any political party."
    )

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
                "description": short_desc,
                "tags": tags,
                "categoryId": "25",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        },
        timeout=30,
    )
    init_resp.raise_for_status()
    upload_url = init_resp.headers["Location"]

    with open(short_path, "rb") as f:
        video_data = f.read()

    log(f"  Uploading {len(video_data) / (1024*1024):.1f} MB short...")
    upload_resp = requests.put(
        upload_url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "video/mp4",
            "Content-Length": str(len(video_data)),
        },
        data=video_data,
        timeout=300,
    )
    upload_resp.raise_for_status()
    short_id = upload_resp.json()["id"]
    log(f"  Short uploaded: https://youtube.com/shorts/{short_id}")
    return short_id


# ── Main Pipeline ──────────────────────────────────────────────────────────────

def main():
    log("=" * 60)
    log("YouTube Political Channel Daily Pipeline")
    log("=" * 60)

    # Create output directory for this run
    output_dir = tempfile.mkdtemp(prefix="pipeline_")
    log(f"Output dir: {output_dir}")

    # Step 1: Fetch RSS
    rss_text = fetch_rss()

    # Step 2: Pick topic
    topic_data = pick_topic(rss_text)

    # Step 3: Write script
    script_data = write_script(topic_data)
    log(f"  Script length: {len(script_data['script'])} chars")

    # Step 4: Generate YouTube metadata
    metadata = generate_metadata(topic_data, script_data["script"])
    log(f"  Title: {metadata['title']}")

    # Step 5: Generate TTS
    audio_data = generate_tts(script_data["script"])

    # Save audio to disk for local rendering
    audio_path = os.path.join(output_dir, "voiceover.mp3")
    with open(audio_path, "wb") as f:
        f.write(audio_data)
    log(f"  Audio saved: {audio_path} ({len(audio_data)} bytes)")

    # Step 6: Render thumbnail locally
    thumbnail_path = render_thumbnail_local(topic_data, metadata, output_dir)

    # Step 7: Render video locally (this is the longest step)
    video_path = render_video_local(audio_path, topic_data, script_data, output_dir)

    # Step 8: Upload main video to YouTube
    upload_to_youtube(video_path, thumbnail_path, metadata)

    # Step 9: Render and upload YouTube Short
    try:
        short_path = render_short(video_path, audio_path, topic_data, script_data, output_dir)
        upload_short_to_youtube(short_path, metadata)
    except Exception as e:
        log(f"  WARNING: Short generation/upload failed: {e}")
        log("  Main video was uploaded successfully.")

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
