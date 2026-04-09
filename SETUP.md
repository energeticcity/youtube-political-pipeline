# The Political Lens — YouTube Pipeline Setup

Automated daily political video pipeline. Fetches trending news, writes a script with AI, generates voiceover, renders a professional video, and uploads to YouTube.

## Architecture

```
Google News RSS → Claude (pick topic) → Claude (write script) → Claude (metadata/SEO)
    → ElevenLabs TTS → Pillow + FFmpeg (render video & thumbnail) → YouTube upload
```

Runs daily at 10am ET via GitHub Actions.

## Quick Start

### 1. Create a GitHub repo
Push this folder to a new private GitHub repo.

### 2. Get API keys
You need:
- **Anthropic API key** — https://console.anthropic.com
- **ElevenLabs API key** — https://elevenlabs.io (needs credits for TTS)
- **YouTube OAuth credentials** — See step 3

### 3. Set up YouTube OAuth
1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new project (or use existing)
3. Enable the **YouTube Data API v3**
4. Create an **OAuth 2.0 Client ID** (Desktop app type)
5. Run the helper script locally:
   ```
   pip install requests
   python get_youtube_token.py
   ```
6. Authorize in the browser when prompted
7. Copy the refresh token it outputs

### 4. Add GitHub Secrets
Go to your repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret Name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `ELEVENLABS_API_KEY` | Your ElevenLabs API key |
| `YOUTUBE_CLIENT_ID` | OAuth Client ID from step 3 |
| `YOUTUBE_CLIENT_SECRET` | OAuth Client Secret from step 3 |
| `YOUTUBE_REFRESH_TOKEN` | Refresh token from step 3 |
| `YOUTUBE_CHANNEL_ID` | Your YouTube channel ID (starts with UC...) |

### 5. Test it
Go to Actions tab → "Daily Political Video Pipeline" → "Run workflow" to trigger manually.

## File Structure

```
├── pipeline.py          # Main orchestrator
├── video_renderer.py    # Custom Pillow + FFmpeg video/thumbnail renderer
├── get_youtube_token.py # One-time OAuth setup helper
├── requirements.txt     # Python dependencies
├── fonts/               # Montserrat font files (bundled)
└── .github/workflows/
    └── daily-video.yml  # GitHub Actions cron job
```

## Customization

- **Channel branding**: Edit colors and text in `video_renderer.py` (RED_ACCENT, channel_name, etc.)
- **Schedule**: Edit the cron in `.github/workflows/daily-video.yml`
- **Voice**: Change `ELEVENLABS_VOICE_ID` in `pipeline.py`
- **Topics**: Modify the RSS query or Claude prompt in `fetch_rss()` / `pick_topic()`
- **Background videos**: Update the `BG_VIDEOS` dict in `pipeline.py` with your own stock footage URLs
