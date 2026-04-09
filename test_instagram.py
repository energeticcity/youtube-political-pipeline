#!/usr/bin/env python3
"""Quick test: download the latest Short from GitHub Release and upload to Instagram."""
import os
import sys
import requests

INSTAGRAM_USERNAME = os.environ.get("INSTAGRAM_USERNAME", "")
INSTAGRAM_PASSWORD = os.environ.get("INSTAGRAM_PASSWORD", "")

SHORT_URL = "https://github.com/energeticcity/youtube-political-pipeline/releases/download/v20260409-1428/short_v20260409-1428.mp4"

def main():
    if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
        print("ERROR: INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD env vars required")
        sys.exit(1)

    print(f"Instagram username: {INSTAGRAM_USERNAME[:3]}***")

    # Download the short
    print(f"Downloading short from GitHub Release...")
    resp = requests.get(SHORT_URL, timeout=60, allow_redirects=True)
    resp.raise_for_status()
    short_path = "/tmp/test_short.mp4"
    with open(short_path, "wb") as f:
        f.write(resp.content)
    print(f"  Downloaded: {len(resp.content) / 1024 / 1024:.1f} MB")

    # Try Instagram upload
    print("Attempting Instagram login...")
    import signal
    from instagrapi import Client

    class InstagramTimeout(Exception):
        pass

    def _timeout_handler(signum, frame):
        raise InstagramTimeout("Instagram operation timed out (120s)")

    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(120)

    try:
        cl = Client()
        cl.set_user_agent("Instagram 269.0.0.18.75 Android (33/13; 420dpi; 1080x2400; samsung; SM-G991B; o1s; exynos2100)")
        cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
        print("  Login successful!")

        caption = (
            "US political leaders react as Trump announces ceasefire\n\n"
            "Watch the full analysis on YouTube: The Political Lens\n\n"
            "#politics #news #politicalnews #shorts #politicalanalysis #breakingnews\n\n"
            "AI-generated political analysis."
        )

        print("  Uploading Reel...")
        media = cl.clip_upload(short_path, caption=caption)
        print(f"  SUCCESS! Reel posted: https://instagram.com/reel/{media.code}")

    except InstagramTimeout:
        print("  FAILED: Instagram operation timed out (120s) - likely login challenge")
    except Exception as e:
        print(f"  FAILED: {e}")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

if __name__ == "__main__":
    main()
