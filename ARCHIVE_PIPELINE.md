# The Past Was Ridiculous

Replaces the dad-joke schedule with original historical commentary over checked archival footage. No Vyro or HeyGen account is needed. Existing Gemini credentials supply source-grounded story writing and automated editorial checks; existing ElevenLabs credentials supply the narrator. Existing Post for Me credentials are used only in the separate publishing workflow.

## What runs

- Three daily automatic production/posting opportunities at 14:07, 18:07 and 22:07 UTC (07:07, 11:07 and 15:07 Dawson Creek time). At most one story per run. GitHub queuing and rendering can delay the actual publication time.
- The two curated starter stories run first. When those are exhausted, automatic refill discovers unused Prelinger films, requires an explicit public-domain label, samples footage, writes an original story, and independently checks its selected shots and claims. No manual story entry or per-video approval is required.
- Check the live Prelinger rights label, download the pinned file, verify SHA-256, generate original narration with exact timestamps, assemble 1080×1920 H.264 video and captions, and save an Actions artifact for 30 days.
- Original film sound/music is never included. Narration is AI-generated and disclosed. No impersonation, cloned celebrity voice, or synthetic historical footage.
- After artifact upload, a GitHub issue records the episode as previewed. Source reservation issues prevent automatic film reuse, even after failure. Explicit manual episode selection regenerates catalogue previews; `episode=auto` forces a fresh generated preview. Branch previews cannot publish or reserve production sources.
- Metadata and footage are evidence, never instructions. The generator rejects unsupported claims and unsuitable footage and compares recent scripts for repetition. Automated review is imperfect and cannot guarantee historical accuracy, monetization, or worldwide rights clearance.
- Discovery is bounded to 30 item checks and at most 3 qualified generation attempts per run, with 250 MiB/30-minute source limits. A failed main-branch slot creates an issue. API outages, exhausted suitable sources, or rejected stories can leave a slot empty.
- Generated stories, source fingerprints and editorial evidence travel in the trusted preview manifest. Publication checks the originating workflow, main branch, catalogue fingerprint, current refill policy, source rights and video fingerprint.

## Publication controls

On 2026-09-03 the user explicitly requested automatic posting without per-video approval on the previous schedule. All enabled catalogue stories publish automatically after successful generation and verification while both master publishing switches are enabled. There is no per-episode approval gate. Rights verification, source fingerprints, narration checks and duplicate locks remain enforced. The pilot was first submitted through the manual workflow. Use **Check Archive Delivery** with its Post for Me ID to read per-platform results without reposting.

Review the MP4, script, source evidence, caption alignment and account destinations first. Monetization is neither enabled nor guaranteed by this change. Public-domain archive labels are evidence, not worldwide legal clearance. Check territory-specific rights when necessary. YouTube independently assesses original value and repetitive/reused content.

Configure repository variables after review:

1. `CLIP_DESTINATIONS_JSON`: explicit existing Post for Me IDs, e.g. `{"youtube":"account_id","instagram":"account_id","tiktok":"account_id"}`. No default or first-account selection: every configured ID is checked against its platform. Connect/verify the same YouTube channel in Post for Me before using that route; the legacy direct YouTube uploader is not invoked.
2. `CLIP_PUBLISH_ENABLED=true` permits the manual **Publish Reviewed Archive Story** action. Supply a successful main-branch preview run ID. No public post is created by the preview action.
3. Ongoing automatic publishing requires `CLIP_AUTO_PUBLISH_ENABLED=true`. Every enabled catalogue episode is eligible without a separate user approval. A successful scheduled/main preview triggers publishing. Catalogue changes still require a fresh preview so its fingerprint matches.

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

## Read-only operational health check

Run `python archive_healthcheck.py` from an authorized checkout with an existing
`gh` login. It reads publishing switches, 100 recent Actions runs, the complete
publication ledger (including closed locks), and up to five completed delivery
checks. It never generates a story, spends narration credits, submits a post,
changes a switch, or creates a monitor. Missing delivery evidence remains
unverified, even when a publish workflow succeeded.

For a queued or ambiguous post, use the existing read-only workflow:

```
gh workflow run archive-delivery.yml --repo energeticcity/youtube-political-pipeline -f post_id=POST_ID
```

Wait for that run to finish before taking another snapshot. Inspect per-platform
results and individual video URLs. A TikTok profile URL does not identify a
specific published video. A failed provider upload quota cannot be repaired by
blind retries or by switching credentials/providers. Preserve publication locks;
only consider an existing platform-specific recovery after its failure is
confirmed and its cause is resolved.

Refill keeps the same 30 metadata-check / three generation-attempt limits and
public-domain/year/credit/size gates. Rotating search results are considered
before the popular-page fallback, and results rotate within each page. The
`archive-refill-diagnostics` artifact records only counts and outcome, including
bounded discovery exhaustion; it contains no provider error bodies or credentials.

For deeper YouTube recovery evidence, dispatch the same read-only workflow with
`-f inspect_recovery=true`. Its `recovery-check.json` reads the original post,
configured YouTube account, paginated results and existing post references. It
extracts fixed quota labels without exporting transport diagnostics or media
URLs. The check always holds recovery: it cannot verify live project quota,
source rights, video fingerprints, all GitHub locks, external manual recovery or
billing allowance. It never submits, updates or retries a post. A provider
`external_id` is a reference, not a verified API idempotency guarantee.

## Creative format and quality

New generated stories use3–6grounded beats/50–85words, targeting25–35seconds, with an immediately visible premise and one earned payoff. Modest horizontal framing up to1.2×may be proposed only when subject/context are retained; independent editorial review sees the actual framed source images. No blind portrait crop or uninspected extra cuts. Exact TTS character timings drive phrase captions. Permanent branding/headlines are reduced, with source credits and AI disclosure preserved.

After rendering, the existing configured Gemini model independently hears the actual final soundtrack and transcribes without the proposed script. Material audible issues or transcript mismatch block publication; no automatic paid regeneration. This is limited to one20–60second audio review per run. Transcript/listening notes stay off artifacts/logs; only pass/model/video fingerprint evidence enters the manifest. Publishing requires the audio pass fingerprint to match the clip. This check is audio quality evidence, not a view-uplift measurement.

Existing previews can be auditioned with archive-audio-review.yml without generating a new voice or publishing. Temporary daily-video audio-review dispatches suppress artifact upload and publication. Private platform analytics must use an approved private execution path; never export them to this public repository.

Compare creative outcomes by platform at24hours and7days after actual publication. Treat upload failures separately from creative performance; unavailable metrics are missing, never zero. Use engaged views, stayed-to-watch and retention/average duration where authorized access supplies them. Sparse public view counts do not prove a winning approach. No extra public cadence slots or source-lock resets are permitted.
