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

## Guarded YouTube-only recovery

`archive-youtube-recovery.yml` is manual and defaults to validation only. It shares
`archive-publication` serialization. It never regenerates narration/video, changes
an old manifest/digest, uploads replacement media, edits an original provider post,
or includes Instagram/TikTok. A successful validation is not publication.

The original successful main preview must match its catalogue, source/rules,
video hash and durable publication ledger. A changed policy triggers actual
revalidation rather than accepting the old digest: current word/beat/source bounds,
fresh explicit rights and downloaded source hash, recent-story duplication,
independent current-policy review of the actual rendered frames, and actual-audio
review bound to exact MP4 bytes. At most one editorial and one audio review; no
voice generation or automatic retries. Cheap structural failures stop before paid
reviews. Private review notes/transcripts stay in memory.

Submission additionally requires publishing switches enabled and YouTube unpaused,
connected exact configured account, terminal daily-quota failure before upload with
no video reference, no matching feed video, complete provider pagination, no original
or recovery duplicate and no durable retry lock (including closed issues). Original
provider media is downloaded and its hash must match the reviewed artifact. A
reservation is written before exactly one new YouTube-only POST; ambiguity retains
it. Check the new post's individual video URL separately; queued is not published.

Reset time does not prove capacity or allowance. An existing repository administrator
must provide fresh factual evidence in an issue titled
`[archive-youtube-recovery-evidence] ORIGINAL_POST_ID`. Its JSON body binds
`post_id`, `youtube_account_id`, `youtube_channel_id`, `video_sha256`, `current_policy_digest`,
`project_number` (currently `823315471809`), timezone-aware `verified_at` within an
hour, numeric `available_uploads` >=1, and true facts `no_extra_spend`,
`within_existing_cadence_and_budget`, `no_manual_channel_duplicate`.
`capacity_evidence_url`, `billing_evidence_url`, `channel_review_url` identify the
read-only evidence; do not include tokens, private analytics or signed media URLs.
`replacement_failed_run_id` must be an actual failed scheduled main preview within
24hours. That failed slot can be used only once, including closed reservation history.
This records external facts that the API cannot verify; it is not routine per-video
creative approval or permission to purchase/expand access. If the facts are unknown,
keep submission held.

The original Oct4 long-distance clip has99words and fails the current50–85word rule.
Its unchanged artifact cannot be recovered through this path. Do not edit the proof,
weaken the gate, clear its source lock or re-render it simply to fill a missed slot.

## Durable calendar-slot admission

The three UTC times remain14:07/18:07/22:07, now expressed as three separate cron
entries so `github.event.schedule` distinguishes the hour. GitHub exposes the cron,
not an original nominal occurrence timestamp. Admission records observed run creation
time and a bounded calendar occupancy decision; it does not invent event provenance.
Scheduled run creation must be within2minutes before/30minutes after that hour's
occurrence, and generation cannot start before it is due. Legacy combined cron and
late/ambiguous events hold without paid work. A queued job uses its run creation time,
not its eventual start time, for identity.

Manual production recovery supplies `slot_utc=YYYY-MM-DDTHH:07:00Z` for an existing,
due slot on the same UTC date. It is bounded to3hours late and must leave the30minute
workflow runtime before the next slot/day boundary. No future, extra or backlog slots.
First reconcile pre-rollout queued/running previews and publication jobs. If any old
run is active or uncertain, hold recovery. GitHub documents schedules using the latest
default-branch commit; mandatory generation proof also blocks a legacy workflow that
loads new pipeline code without its admission step. Mandatory publication proof blocks
old/no-proof artifacts even if an old runner generated them. Do not claim control over
unobservable GitHub queues; inspect actual run/commit state again before recovery.

`archive-previews` serialization protects a durable `[archive-slot] UTC_OCCURRENCE`
issue written before generation. Scheduled and manual contenders use the same key.
Closing the issue, rerunning, preparation failure or a crash never releases it. The
receipt binds run ID, run attempt and nonce. Production code requires that receipt
before source preparation or narration. Source/publication locks remain independent.

After artifact upload, the original owner marks `preview_ready` with manifest/video
fingerprints. The publisher checks the successful main run and matching attempt,
then reserves `publishing` under existing `archive-publication` serialization before
provider side effects. Partial success, pending acceptance or a crash permanently
hold a second attempt. `submission_attempt_finished` is not publication proof: inspect
per-platform results and individual URLs. Never reopen a slot or regenerate to replay
accepted/ambiguous platforms. Crash recovery starts with retained artifact/claim and
provider/source/publication ledgers, not a new generation or automatic retry.

The hourly health snapshot includes slot owners/phases. A held scheduled workflow can
finish successfully without an artifact or post; no exclusive ready slot means the
publisher skips it. That success is not a filled slot. Rights, current creative/audio
policy, destination switches/accounts, media hashes and bounded generation limits
continue to gate every admitted story.

## Prospective temporal writing evidence

The writer formerly saw 30 isolated start frames while the independent reviewer saw
selected shots at 0/4/9/13 seconds. That repeatable evidence asymmetry lets a draft
infer action or context that later frames contradict. The writer now receives the
same temporal offsets for seven shot options: 28 images within the unchanged 30-image
cap. This trades some search breadth for inspected shot context; it does not establish
the historical cause of a rejection or measured performance uplift. Each allowed start
remains inspected and within the 14-second source bound. Reframing, narration bounds,
recent-story duplication, independent review and all publishing gates remain.

Still two model calls per candidate (writer/reviewer), three candidates maximum and
one audio review only after a passing story; no corrective generation retry or source
reservation release. Rejections retain only candidate/source fingerprints, allowed
starts and allowlisted editorial reason codes. Free-text review notes, scripts,
provider payloads and transcripts are not exported. Missing/unrecognized codes stay
unclassified, never inferred from discarded notes. Successful review is normalized to
the existing strict `{pass:true,issues:[]}` proof; added diagnostic fields cannot cause
a false publisher mismatch. Slot 230 and its rejected sources remain occupied.


## Caption packing recovery

Run 37480576048 passed the source/editorial check but failed rendering: the
52-character phrase “How did mid-century department stores guarantee that”
cannot pack whole words into two 29-character rows. Phrase grouping now tests
the actual unchanged two-row layout before adding each word, splitting at its
original narration timestamps. Orphan-tail balancing also validates both proposed
segments; a valid one-word tail is preferable to overflowing the safe width.
Oversized individual words still fail closed. Font, width, row count, narration,
source/editorial/audio gates and budgets remain unchanged. This prospective repair
does not release occupied slot 248 or reserved source quality_control_1; the failed
run retained no complete media artifact for safe replay.


## Failed preparation capability inspection

`archive-preparation-recovery.yml` is a manual, GET-only prerequisite inspector,
not a retry or publisher. It requires an occupied `preparation_failed` slot, its
terminal original main run with only the build step failed, the original bot-owned
passed source created during that run, and no publication reservation. It checks
all configured accounts and exact provider external references; any existing request
holds regeneration regardless of its status. It then inspects existing ElevenLabs
TTS history within the original run’s time bounds for the exact voice/model/script.
Only a unique match with exact character alignment and readable bounded audio is
reported available. History IDs, audio, alignments, text and provider account payloads
stay in memory; exported evidence contains booleans and fingerprints only. It never
changes slots/source locks, performs model/TTS generation, or submits a post. Missing
history permission is a hold requiring an existing authorized read surface, not an
invitation to change credentials or permissions. This capability alone cannot restore
lost reviewed shot starts/source fingerprints or authorize recovery of slot 248.
