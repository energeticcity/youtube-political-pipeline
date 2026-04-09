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

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = "energeticcity/youtube-political-pipeline"

INSTAGRAM_USERNAME = os.environ.get("INSTAGRAM_USERNAME", "")
INSTAGRAM_PASSWORD = os.environ.get("INSTAGRAM_PASSWORD", "")
TIKTOK_USERNAME = os.environ.get("TIKTOK_USERNAME", "")
TIKTOK_PASSWORD = os.environ.get("TIKTOK_PASSWORD", "")

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
    headlines = []

    # Fetch from multiple queries to get diverse, breaking stories
    queries = [
        "US politics breaking news today",
        "congress senate president white house today",
        "US political news latest",
    ]
    for query in queries:
        try:
            resp = requests.get(
                "https://news.google.com/rss/search",
                params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
                headers={"User-Agent": "Mozilla/5.0 (compatible; RSS reader)"},
                timeout=15,
            )
            resp.raise_for_status()
            headlines.append(resp.text[:3000])
        except Exception as e:
            log(f"  RSS query '{query}' failed: {e}")

    text = "\n---\n".join(headlines)
    log(f"  Got {len(text)} chars of RSS data from {len(headlines)} feeds")
    return text


# ── Step 2: Pick a topic ──────────────────────────────────────────────────────

def pick_topic(rss_text: str) -> dict:
    import random
    log("Asking Claude to pick a topic...")

    # Add randomization to avoid always picking the same story
    seed_word = random.choice(["surprising", "controversial", "impactful", "urgent", "explosive", "developing"])
    time_hint = random.choice(["in the last few hours", "breaking today", "just announced", "developing right now"])

    result = call_claude(
        system="You are a YouTube political news selector. You MUST pick a story directly from the headlines provided. Respond ONLY with the exact XML format. No other text.",
        user_message=f"""Here are TODAY's top political news headlines from Google News RSS:

{rss_text}

---
CRITICAL RULES:
1. Pick the single most {seed_word} political story that is {time_hint}.
2. You MUST select from the ACTUAL headlines above. Do NOT invent topics or pick evergreen subjects.
3. The topic MUST reference a specific person, event, bill, vote, action, or announcement from the headlines.
4. Do NOT pick generic topics like "25th Amendment" or "government shutdown" unless that is literally in today's headlines.
5. Prefer stories about specific actions taken TODAY: votes, speeches, executive orders, indictments, rulings, deals, etc.
6. Your <TOPIC> should closely match or paraphrase an actual headline from above.

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


# ── Step 11: Upload Short to Instagram Reels ──────────────────────────────────

def upload_to_instagram(short_path: str, metadata: dict):
    """Upload Short as an Instagram Reel using instagrapi."""
    if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
        log("Instagram upload skipped (no credentials)")
        return None

    log("Uploading to Instagram Reels...")
    try:
        from instagrapi import Client

        cl = Client()
        # Set user agent to look like a real device
        cl.set_user_agent("Instagram 269.0.0.18.75 Android (33/13; 420dpi; 1080x2400; samsung; SM-G991B; o1s; exynos2100)")

        # Check for saved session to avoid repeated logins
        session_file = "/tmp/ig_session.json"
        try:
            if os.path.exists(session_file):
                cl.load_settings(session_file)
                cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                log("  Instagram: restored session")
            else:
                cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                cl.dump_settings(session_file)
                log("  Instagram: fresh login")
        except Exception as login_err:
            log(f"  Instagram: session restore failed ({login_err}), doing fresh login...")
            cl = Client()
            cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            cl.dump_settings(session_file)

        # Build caption for Reel
        title = metadata.get("title", "The Political Lens")
        caption = (
            f"{title}\n\n"
            f"Watch the full analysis on YouTube: The Political Lens\n\n"
            f"#politics #news #politicalnews #shorts #politicalanalysis #breakingnews\n\n"
            f"AI-generated political analysis."
        )

        # Upload as Reel
        media = cl.clip_upload(short_path, caption=caption)
        reel_id = media.pk
        log(f"  Instagram Reel posted: https://instagram.com/reel/{media.code}")
        return reel_id

    except Exception as e:
        log(f"  WARNING: Instagram upload failed: {e}")
        return None


# ── Step 12: Upload Short to TikTok ──────────────────────────────────────────

def upload_to_tiktok(short_path: str, metadata: dict):
    """Upload Short to TikTok using tiktok-uploader (Playwright-based)."""
    if not TIKTOK_USERNAME or not TIKTOK_PASSWORD:
        log("TikTok upload skipped (no credentials)")
        return None

    log("Uploading to TikTok...")
    try:
        from tiktok_uploader.upload import upload_video
        from tiktok_uploader.auth import AuthBackend

        title = metadata.get("title", "The Political Lens")
        # TikTok captions are limited, keep it punchy
        caption = f"{title} #politics #news #politicalnews #fyp #foryou"
        if len(caption) > 150:
            caption = caption[:147] + "..."

        # Try cookie-based auth first
        cookie_file = "/tmp/tiktok_cookies.json"
        if os.path.exists(cookie_file):
            log("  TikTok: using saved cookies")
            upload_video(
                short_path,
                description=caption,
                cookies=cookie_file,
                headless=True,
            )
        else:
            log("  TikTok: no cookies found, skipping (manual cookie setup needed)")
            log("  To set up: export TikTok cookies from your browser as JSON")
            log("  and save as TIKTOK_COOKIES GitHub secret")
            return None

        log(f"  TikTok video posted!")
        return True

    except Exception as e:
        log(f"  WARNING: TikTok upload failed: {e}")
        return None


# ── Step 13: Upload Short to GitHub Release & Update RSS Feed ─────────────────

def upload_short_to_github_release(short_path: str, tag_name: str) -> str:
    """Upload the Short MP4 as a GitHub Release asset. Returns the public download URL."""
    if not GITHUB_TOKEN:
        log("GitHub Release upload skipped (no GITHUB_TOKEN)")
        return ""

    log("Uploading Short to GitHub Release...")
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    # Create release
    release_data = {
        "tag_name": tag_name,
        "name": f"Short {tag_name}",
        "body": "Auto-generated Short video for cross-platform distribution.",
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
        # Release with this tag may already exist — get it
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{tag_name}",
            headers=headers, timeout=15,
        )
        resp.raise_for_status()

    release = resp.json()
    upload_url = release["upload_url"].replace("{?name,label}", "")

    # Upload the MP4 asset
    filename = f"short_{tag_name}.mp4"
    with open(short_path, "rb") as f:
        video_data = f.read()

    log(f"  Uploading {len(video_data) / (1024*1024):.1f} MB to release {tag_name}...")
    asset_resp = requests.post(
        f"{upload_url}?name={filename}",
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Content-Type": "application/octet-stream",
        },
        data=video_data,
        timeout=300,
    )
    asset_resp.raise_for_status()
    download_url = asset_resp.json()["browser_download_url"]
    log(f"  Short available at: {download_url}")
    return download_url


def update_rss_feed(video_url: str, metadata: dict, thumbnail_url: str = "", youtube_short_id: str = ""):
    """Update the RSS feed XML in the repo with the new Short video entry."""
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

    # Fetch existing feed.xml (or start fresh)
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

    # Parse or create feed
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    if existing_xml:
        try:
            root = ET.fromstring(existing_xml)
            channel = root.find("channel")
        except ET.ParseError:
            channel = None
    else:
        channel = None

    if channel is None:
        # Build fresh RSS feed
        root = ET.Element("rss", version="2.0", attrib={
            "xmlns:media": "http://search.yahoo.com/mrss/",
            "xmlns:atom": "http://www.w3.org/2005/Atom",
        })
        channel = ET.SubElement(root, "channel")
        ET.SubElement(channel, "title").text = "The Political Lens - Shorts"
        ET.SubElement(channel, "link").text = f"https://github.com/{GITHUB_REPO}"
        ET.SubElement(channel, "description").text = "Daily AI-powered political analysis shorts for TikTok and Instagram"
        ET.SubElement(channel, "language").text = "en-us"

    # Update lastBuildDate
    last_build = channel.find("lastBuildDate")
    if last_build is None:
        last_build = ET.SubElement(channel, "lastBuildDate")
    last_build.text = now

    # Add new item at the top (after channel metadata)
    item = ET.Element("item")
    ET.SubElement(item, "title").text = metadata.get("title", "Political Lens Short")

    # Build a concise description with video download link
    # Keep it short to avoid bloating the feed
    desc_parts = []
    full_desc = metadata.get("description", "")
    # Take just the first 2 sentences of the description
    sentences = full_desc.split(".")
    short_desc = ". ".join(sentences[:2]).strip()
    if short_desc and not short_desc.endswith("."):
        short_desc += "."
    desc_parts.append(short_desc)

    if video_url:
        desc_parts.append(f"\nVideo: {video_url}")
    if youtube_short_id:
        desc_parts.append(f"\nWatch: https://youtube.com/shorts/{youtube_short_id}")

    desc_parts.append("\n#politics #news #politicalnews #shorts")
    ET.SubElement(item, "description").text = "\n".join(desc_parts)

    # Link to YouTube Short if available
    if youtube_short_id:
        ET.SubElement(item, "link").text = f"https://youtube.com/shorts/{youtube_short_id}"
        ET.SubElement(item, "guid", isPermaLink="true").text = f"https://youtube.com/shorts/{youtube_short_id}"
    elif video_url:
        ET.SubElement(item, "link").text = video_url
        ET.SubElement(item, "guid", isPermaLink="false").text = video_url

    ET.SubElement(item, "pubDate").text = now

    # NOTE: No <enclosure> or media:content tags — these cause dlvr.it
    # to try downloading the full MP4, exceeding their 15MB feed size limit.
    # The video download URL is included in the description text instead.

    # Insert item after channel metadata (before other items)
    items = channel.findall("item")
    if items:
        idx = list(channel).index(items[0])
        channel.insert(idx, item)
    else:
        channel.append(item)

    # Keep only last 20 items
    all_items = channel.findall("item")
    for old_item in all_items[20:]:
        channel.remove(old_item)

    # Serialize
    ET.indent(root, space="  ")
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")

    # Push to GitHub
    push_data = {
        "message": f"Update RSS feed: {metadata.get('title', 'new short')}",
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

    # Step 9: Render YouTube Short
    short_path = None
    short_id = None
    try:
        short_path = render_short(video_path, audio_path, topic_data, script_data, output_dir)
    except Exception as e:
        log(f"  WARNING: Short rendering failed: {e}")

    # Step 10: Upload Short to YouTube
    if short_path:
        try:
            short_id = upload_short_to_youtube(short_path, metadata)
        except Exception as e:
            log(f"  WARNING: YouTube Short upload failed: {e}")

    # Step 11: Upload to Instagram Reels
    if short_path:
        try:
            upload_to_instagram(short_path, metadata)
        except Exception as e:
            log(f"  WARNING: Instagram upload failed: {e}")

    # Step 12: Upload to TikTok
    if short_path:
        try:
            upload_to_tiktok(short_path, metadata)
        except Exception as e:
            log(f"  WARNING: TikTok upload failed: {e}")

    # Step 13: Upload Short to GitHub Release for backup/RSS access
    if short_path:
        try:
            from datetime import datetime, timezone
            tag = datetime.now(timezone.utc).strftime("v%Y%m%d-%H%M")
            video_download_url = upload_short_to_github_release(short_path, tag)
            update_rss_feed(
                video_url=video_download_url,
                metadata=metadata,
                youtube_short_id=short_id or "",
            )
        except Exception as e:
            log(f"  WARNING: GitHub Release/RSS update failed: {e}")

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
