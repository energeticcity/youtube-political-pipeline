#!/usr/bin/env python3
"""
Repost an existing video to all connected Post for Me social accounts.
Reuses the main pipeline's post_via_postforme() — no HeyGen render, no new
ElevenLabs audio, no Gemini metadata. Just takes a video URL + caption + title
and fires them to every connected platform.

Triggered manually from the GitHub Actions UI (repost.yml workflow).

Env vars:
  VIDEO_URL       — public MP4 URL (required)
  CAPTION         — caption/description text (required)
  TITLE           — title for YouTube (optional, defaults to caption first 60 chars)
  POSTFORME_API_KEY — required
"""

import os
import sys

# Reuse the same integration from the main pipeline
from pipeline import post_via_postforme, notify_for_tiktok, log


def main():
    video_url = os.environ.get("VIDEO_URL", "").strip()
    caption = os.environ.get("CAPTION", "").strip()
    title = os.environ.get("TITLE", "").strip() or caption[:60]

    if not video_url or not caption:
        log("ERROR: VIDEO_URL and CAPTION are required")
        sys.exit(1)

    log("=" * 60)
    log("Post for Me — repost existing video")
    log("=" * 60)
    log(f"  Video: {video_url}")
    log(f"  Title: {title}")
    log(f"  Caption: {caption[:120]}{'...' if len(caption) > 120 else ''}")

    post_id, targets = post_via_postforme(video_url, caption, title)
    if post_id:
        log(f"SUCCESS: queued to {targets} (post_id={post_id})")
    else:
        log("FAILED: no post_id returned — check Post for Me dashboard")
        sys.exit(1)


if __name__ == "__main__":
    main()
