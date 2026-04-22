# Two Dad Jokes Daily

Automated pipeline that posts two dad joke videos a day to YouTube Shorts, then auto-cross-posts to TikTok and Instagram via Publer reading the RSS feed.

Each run:
1. Pulls a clean dad joke from r/dadjokes (Gemini fallback if nothing usable).
2. Generates voiceover with ElevenLabs.
3. Animates the "Hank" avatar talking via the HeyGen API.
4. Renders intro/outro cards + on-screen captions with ffmpeg.
5. Uploads to YouTube as a Short.
6. Updates `feed.xml` so Publer auto-posts to TikTok and Instagram.

The previous political-news version of this pipeline lives on the [`political-archive`](https://github.com/energeticcity/youtube-political-pipeline/tree/political-archive) branch.

## Required GitHub Secrets

| Secret | Purpose |
|---|---|
| `GEMINI_API_KEY` | Joke fallback + metadata generation |
| `ELEVENLABS_API_KEY` | TTS voiceover |
| `ELEVENLABS_VOICE_ID` | Voice ID for the "dad" voice (e.g. `XmUeU0FRyne67Dy7UaT4`) |
| `HEYGEN_API_KEY` | Talking-avatar video generation |
| `HEYGEN_AVATAR_ID` | The default Photo Avatar ID for Hank in HeyGen |
| `HEYGEN_AVATAR_IDS_EXTRA` | (Optional) Comma-separated additional Photo Avatar IDs for expression variety — e.g. `id_surprised,id_facepalm,id_smirk`. Pipeline picks one per joke. |
| `ELEVENLABS_MODEL_ID` | (Optional) Override ElevenLabs model. Defaults to `eleven_v3` (expressive). Set to `eleven_multilingual_v2` to fall back if v3 is unavailable for your voice. |
| `YOUTUBE_CLIENT_ID` | YouTube OAuth |
| `YOUTUBE_CLIENT_SECRET` | YouTube OAuth |
| `YOUTUBE_REFRESH_TOKEN` | YouTube OAuth |
| `YOUTUBE_CHANNEL_ID` | YouTube channel ID |

## One-time setup

1. **Generate Hank's portrait** (the dad character). Save as `dad_avatar.jpg` in the repo root.
2. **Upload Hank to HeyGen as a Photo Avatar.** Avatars → Create Avatar → Photo Avatar → upload `dad_avatar.jpg`. Copy the avatar ID and set as `HEYGEN_AVATAR_ID`.
3. **Sign up for HeyGen Creator API tier ($24/mo)** for API access. Generate an API key under Space Settings → API. Set as `HEYGEN_API_KEY`.
4. **Pick a dad voice on ElevenLabs.** Browse the voice library for a warm middle-aged male voice. Set `ELEVENLABS_VOICE_ID`.
5. **Set up Make.com for Instagram + YouTube auto-posting** — see [MAKE_SETUP.md](MAKE_SETUP.md) for detailed step-by-step instructions. Free tier covers both platforms. Replaces both Publer and the in-pipeline YouTube OAuth.
6. **TikTok = manual upload.** Each pipeline run creates a GitHub Issue ("📱 TikTok upload ready") with a phone-friendly download link and a copyable caption. Open the issue email on your phone, save the video, upload to TikTok, add a trending sound. ~30 sec per video.

## Adding extra Hank expressions (optional, makes videos more lively)

Out of the box the pipeline uses one Hank photo for every video. For variety, you can create additional HeyGen Photo Avatars with different expressions and the pipeline will rotate between them automatically.

1. Generate 2–4 new Hank photos in Midjourney. Use the same base prompt but change the expression. Suggested variants:
   - **Surprised**: "...wide-eyed with a surprised open-mouth smile, eyebrows raised..."
   - **Facepalm**: "...palm on forehead, eyes closed, wincing smile..."
   - **Sly smirk**: "...one eyebrow raised, knowing half-smirk, eyes looking slightly off camera..."
   - **Laughing**: "...head tilted back mid-laugh, eyes crinkled shut..."

2. For each photo: HeyGen dashboard → **Avatars** → **Create Avatar** → **Photo Avatar** → upload → note the avatar ID.

3. Add GitHub Secret `HEYGEN_AVATAR_IDS_EXTRA` as a comma-separated list, e.g. `a8d7e2f...,b9c3a1d...,c4e6d2f...`. The default `HEYGEN_AVATAR_ID` stays as-is.

4. Next pipeline run picks one of (default + extras) per video based on joke text. No duplicate renders back-to-back.

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
