# The Past Was Ridiculous

Replaces the dad-joke schedule with original historical commentary over reviewed archival footage. No Vyro, HeyGen, Gemini, or transcription service is needed. Existing ElevenLabs credentials supply the narrator. Existing Post for Me credentials are used only in the separate publishing workflow.

## What runs

- Three daily preview opportunities at the previous schedule times. At most one approved story per run.
- Two curated pilot stories currently exist. This is a finite editorial queue, not unlimited automatic discovery. Add reviewed stories to `archives/episodes.json` to continue.
- Check the live Prelinger rights label, download the pinned file, verify SHA-256, generate original narration with exact timestamps, assemble 1080×1920 H.264 video and captions, and save an Actions artifact for 30 days.
- Original film sound/music is never included. Narration is AI-generated and disclosed. No impersonation, cloned celebrity voice, or synthetic historical footage.
- After successful artifact upload, a GitHub issue records the episode as previewed. Future scheduled runs skip it. Empty queues purchase no narration and publish nothing. Explicit manual episode selection regenerates expired/rejected previews.
- Historical claims are written and checked in the catalogue. We do not ask an LLM to invent facts or ingest arbitrary upload descriptions as instructions.

## Publication controls

The user approved the pilot and this format on 2026-09-03. Both starter episodes are approved for automatic posting; the repository publishing switches are enabled. Future episodes still need explicit editorial approval in the catalogue. The pilot was first submitted through the manual workflow. Use **Check Archive Delivery** with its Post for Me ID to read per-platform results without reposting.

Review the MP4, script, source evidence, caption alignment and account destinations first. Monetization is neither enabled nor guaranteed by this change. Public-domain archive labels are evidence, not worldwide legal clearance. Check territory-specific rights when necessary. YouTube independently assesses original value and repetitive/reused content.

Configure repository variables after review:

1. `CLIP_DESTINATIONS_JSON`: explicit existing Post for Me IDs, e.g. `{"youtube":"account_id","instagram":"account_id","tiktok":"account_id"}`. No default or first-account selection: every configured ID is checked against its platform. Connect/verify the same YouTube channel in Post for Me before using that route; the legacy direct YouTube uploader is not invoked.
2. `CLIP_PUBLISH_ENABLED=true` permits the manual **Publish Reviewed Archive Story** action. Supply a successful main-branch preview run ID. No public post is created by the preview action.
3. Optional ongoing automatic publishing also requires `CLIP_AUTO_PUBLISH_ENABLED=true` and `auto_publish_approved: true` on each episode. Change approval before generating its preview, because the catalogue fingerprint must match. A successful scheduled/main preview then triggers publishing.

Publish runs are serialized. Before any upload/post, an issue `[clip-publication] EPISODE` reserves the episode. That lock remains even when the issue is closed or a provider fails. Check Post for Me per-platform delivery before manually resolving an ambiguous failure; never blindly repost. Provider acceptance means queued, not confirmed published. Issues must remain enabled and ledger issues must not be deleted. Artifact expiration requires a new preview.

There is intentionally no legacy feed.xml update, release-based syndication, or second direct YouTube upload; those routes can duplicate distribution. Old manual rerun/repost workflows remain legacy tools and should not be used for archive stories. The weekly digest still reports legacy metrics, not archive delivery analytics.

## Local checks

Python 3.12+, requests, FFmpeg with libass, and the included Montserrat fonts are required.

```
python -m unittest discover -s tests -v
python archive_pipeline.py check
python archive_pipeline.py preview --episode kitchen-of-tomorrow
```

Preview requires ElevenLabs key/voice environment variables. `--media PATH` uses an already downloaded source but still verifies its hash and current archive metadata. Source videos and secrets are never committed. Preview artifacts contain the finished video, narration, script, subtitles and rights evidence only.

## Source

Design for Dreaming (1956), MPO Productions / General Motors, Prelinger Archives:
https://archive.org/details/Designfo1956

The checked item metadata identifies its licence as `http://creativecommons.org/licenses/publicdomain/`. This catalogue is an allowlist, not a claim that all Internet Archive uploads are reusable. Source hash changes and rights-label changes fail closed.
