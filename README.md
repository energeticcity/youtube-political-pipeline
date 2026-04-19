# Two Dad Jokes Daily

Automated pipeline that posts two dad joke videos a day to YouTube Shorts, then auto-cross-posts to TikTok and Instagram via Publer reading the RSS feed.

Each run:
1. Pulls a clean dad joke from r/dadjokes (Gemini fallback if nothing usable).
2. Generates voiceover with ElevenLabs.
3. Animates a "dad" avatar talking via the D-ID API.
4. Renders intro/outro cards + on-screen captions with ffmpeg.
5. Uploads to YouTube as a Short.
6. Updates `feed.xml` so Publer auto-posts to TikTok and Instagram.

The previous political-news version of this pipeline lives on the [`political-archive`](https://github.com/energeticcity/youtube-political-pipeline/tree/political-archive) branch.

## Required GitHub Secrets

| Secret | Purpose |
|---|---|
| `GEMINI_API_KEY` | Joke fallback + metadata generation |
| `ELEVENLABS_API_KEY` | TTS voiceover |
| `ELEVENLABS_VOICE_ID` | (Optional) Voice ID for the "dad" voice. Defaults to a fallback. |
| `DID_API_KEY` | Talking-avatar video generation |
| `DAD_PHOTO_URL` | (Optional) Public URL to the dad photo. Defaults to `dad_avatar.jpg` in this repo. |
| `YOUTUBE_CLIENT_ID` | YouTube OAuth |
| `YOUTUBE_CLIENT_SECRET` | YouTube OAuth |
| `YOUTUBE_REFRESH_TOKEN` | YouTube OAuth |
| `YOUTUBE_CHANNEL_ID` | YouTube channel ID |

## One-time setup

1. **Pick a dad photo.** Generate one with the prompt: *"friendly middle-aged dad with grey-streaked hair, warm smile, plain neutral background, photorealistic portrait, looking directly at camera, soft studio lighting, square crop"* in Midjourney/DALL-E, or grab a CC0 photo. Save as `dad_avatar.jpg`, commit to repo root, or host elsewhere and set `DAD_PHOTO_URL`.
2. **Pick a "dad" voice on ElevenLabs.** Browse their voice library for a warm, friendly middle-aged male voice. Set `ELEVENLABS_VOICE_ID`.
3. **Sign up for D-ID.** Free trial covers ~5 minutes; the Lite plan is ~$6/mo for ~10 minutes (covers 60 jokes).
4. **Set up Publer.** Connect TikTok + Instagram, then add the RSS feed at `https://raw.githubusercontent.com/energeticcity/youtube-political-pipeline/main/feed.xml` as an auto-post source.

## Schedule

Runs twice daily via GitHub Actions:
- 14:00 UTC (10am ET / 7am PT)
- 22:00 UTC (6pm ET / 3pm PT)

Trigger manually via the **Actions** tab → "Daily Dad Joke Pipeline" → "Run workflow".

## Files

- `pipeline.py` — main orchestration
- `dad_video_renderer.py` — Pillow + ffmpeg compositing
- `feed.xml` — RSS feed (auto-updated each run)
- `fonts/` — Montserrat for captions
- `dad_avatar.jpg` — the dad photo (you provide this)
