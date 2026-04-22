#!/usr/bin/env python3
"""
Retry a previous joke through the audio + video stages without touching
state.json (no episode bump, no monthly_count bump) and without posting to
socials. Useful for validating fixes after a failure.

Required env vars:
  RERUN_SETUP      — joke setup
  RERUN_PUNCHLINE  — joke punchline
  RERUN_EPISODE    — episode number to use in title/badge

Triggered manually via the Actions tab → "Rerun Failed Video".
"""

import os
import sys
import tempfile
from datetime import datetime, timezone

from pipeline import (
    write_script,
    generate_metadata,
    generate_tts,
    denoise_audio,
    upload_to_github_release,
    pick_avatar_id,
    generate_avatar_video,
    upload_video_to_repo,
    get_current_segment,
    log,
)
from dad_video_renderer import render_dad_short


def main():
    setup = os.environ.get("RERUN_SETUP", "").strip()
    punchline = os.environ.get("RERUN_PUNCHLINE", "").strip()
    episode = int(os.environ.get("RERUN_EPISODE", "0") or "0")

    if not setup or not punchline or not episode:
        log("ERROR: RERUN_SETUP, RERUN_PUNCHLINE, RERUN_EPISODE all required")
        sys.exit(1)

    log("=" * 60)
    log(f"Rerun — Episode #{episode}")
    log("=" * 60)
    log(f"  Setup:     {setup}")
    log(f"  Punchline: {punchline}")

    joke = {"setup": setup, "punchline": punchline}
    output_dir = tempfile.mkdtemp(prefix="rerun_")
    tag = datetime.now(timezone.utc).strftime("v%Y%m%d-%H%M") + "-rerun"

    segment = get_current_segment()
    script_data = write_script(joke, episode, segment)
    log(f"  Script: {script_data['script']}")

    metadata = generate_metadata(joke, episode, segment)
    log(f"  Title: {metadata['title']}")

    audio_data = generate_tts(script_data["script"])
    raw_audio_path = os.path.join(output_dir, "voiceover_raw.mp3")
    with open(raw_audio_path, "wb") as f:
        f.write(audio_data)

    audio_path = os.path.join(output_dir, "voiceover.mp3")
    denoise_audio(raw_audio_path, audio_path)

    audio_url = upload_to_github_release(
        audio_path, tag, f"audio_{tag}.mp3", "audio/mpeg"
    )

    avatar_id = pick_avatar_id(joke)
    avatar_path = os.path.join(output_dir, "avatar.mp4")
    generate_avatar_video(audio_url, avatar_path, avatar_id)

    short_path = os.path.join(output_dir, "dad_short.mp4")
    render_dad_short(
        avatar_path=avatar_path,
        joke=joke,
        episode=episode,
        catchphrase=script_data["catchphrase"],
        output_path=short_path,
    )

    video_url = upload_video_to_repo(short_path, f"short_{tag}.mp4")
    log("=" * 60)
    log(f"DONE — preview: {video_url}")
    log("(no social posting, no state changes)")
    log("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"RERUN FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
