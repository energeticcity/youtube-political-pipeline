# Work Log
Last session: 2026-05-10 19:38 MST (Mon May 11 02:38 UTC)

## What I worked on
Long session pushing view-growth optimizations across the entire pipeline. 15 commits, mostly in `pipeline.py` (+630 lines) and `dad_video_renderer.py` (+409 lines).

- **Performance monitoring** (`monitor.py` + `.github/workflows/weekly-digest.yml`): Phase 1 logs per-post metadata to `metrics_log.json` at the end of every render (segment, hook idx, CTA, hashtag set #, joke topic, post_for_me_id). Phase 2 weekly cron (Mondays 13:07 UTC) joins log against Post for Me's `/v1/social-account-feeds?expand=metrics` and creates a GitHub Issue digest with top/bottom 5, segment perf, CTA perf, hashtag-set perf.
- **Hashtag bank rotation**: 20 deterministic hashtag sets cycled by `episode % 20`, plus brand tags shuffled per post and AI tags pick 2 of 5. Combats the documented "same hashtag set every day = spam signal" penalty in 2026.
- **AI disclosure** in every per-platform caption (text-level), plus the existing TikTok API `is_ai_generated: true` flag. Verified with platform docs that there is NO account-level "always disclose AI" toggle on TikTok/IG/YouTube — per-post is the only path. YouTube auto-uploads via Post for Me default to "altered content: No" because Post for Me's API doesn't expose that field — gap acknowledged, manual toggle in YouTube Studio is the workaround.
- **Per-platform captions everywhere**: built once in `_build_platform_captions` (TikTok short/hashtag-heavy, IG story-style, YouTube long-form-with-disclosure), passed to both Post for Me's `platform_configurations` AND written into `feed.xml` under a custom `dadjokefix:*` XML namespace so any RSS consumer can route the right caption per platform.
- **Joke quality filter**: `rate_joke_quality()` asks Gemini to score 1-10, `fetch_dad_joke()` retries up to 6 times for ≥7, falls back to "best of what we saw" before going to Gemini-generated.
- **Per-segment hook variants** + **lower-third HANK chyron** (TV-style name banner first 2.2s) + **tomorrow's joke pre-fetch** (each run pre-fetches one extra joke, stores in `state.json#next_joke`, today's outro card teases its keyword).
- **Pexels b-roll cutaway** during setup (Gemini picks `<BROLLKEYWORD>`, fetches Pexels image, composites into yellow-bordered card overlaid in upper-third for ~1.7s).
- **HeyGen Avatar IV** enabled by default (head sway, blinks, micro-gestures), `talking_style: expressive`, `expression: happy`, native 1080×1920 render, brand-navy background. Adds ~$0.25/video → bumped budget assumptions to $50/mo for 3/day cadence.
- **`monitor.py` weekly digest workflow** + restored 3/day cron schedule (14:07 / 18:07 / 22:07 UTC).

Earlier in the session: viral upgrades (rotating hook banners 9 variations, comment-bait CTA rotation 7 variants, punchline yellow flash, joke-specific topic hashtags via Gemini), more breath/laugh tags in script, ambient music bed, full-screen avatar with Ken Burns + punchline zoom.

## Current state
Pipeline is fully working and shipped to `main`. Last live scheduled run succeeded at 23:03 UTC May 10 ("Why does Waldo only wear stripes?"). Working tree is clean. Avatar IV is on. 3/day cadence configured but **only 2 of 3 daily cron slots are actually firing** in production (see "What to do next").

## What to do next
1. **Investigate the missing lunch cron** (`7 18 * * *`). Last 10 runs only show morning + evening fires — never the 18:07 UTC slot. The cron was added in commit a48456d but GitHub may not have picked it up. Wait through Mon-Tue first, then if still missing: stop+start the workflow OR change all 3 cron entries to clearly distinct minute offsets (e.g. `5 14`, `7 18`, `9 22`).
2. **First weekly digest fires Monday May 18 at 13:07 UTC** (~9:07am ET). Will only have ~7 posts of data — useful patterns probably take 3-4 weeks (~60-80 posts) to surface. Once we have 3-4 digests, feed data back into pipeline: pin winning CTA as default, drop low-performing hashtag sets, lean into best segments.
3. **YouTube AI-content disclosure gap**: Post for Me API doesn't pass the "altered content" flag to YouTube. Either (a) drop the daily 90-sec manual toggle in YouTube Studio for each new upload, or (b) email Post for Me support requesting they add the field.
4. **User-side manual work** still outstanding from research report — these move the needle 10x more than any code change at this point:
   - 7-day account warm-up before scaling cadence (research says skipping this triggers shadowban)
   - 90 min/day in-character comment replies (single highest documented growth lever)
   - Pin a question comment on every post (~37% reply lift)
   - One manual TikTok edit/day with trending sound (in-app, automation-impossible)
   - Newsletter setup (Beehiiv, link in all 3 bios)
   - r/dadjokes text posts 2x/week
   - Cross-stitch/duet 5 mid-tier comedy creators weekly
5. **Optional remaining code work** (diminishing returns):
   - Whisper word-by-word captions (proven 30-50% retention lift on TikTok, ~3 hrs to implement)
   - Performance feedback loop closing — auto-prefer winning CTAs based on monitor data once we have 30+ posts

## Uncommitted changes
All changes committed. Working tree clean, branch up to date with origin/main.

## Open TODOs in code
None added this session.

## Blocked on
- **GitHub Actions cron propagation** for the new 18:07 UTC slot — wait 24-48h, may self-resolve.
- **Real performance data** before we can act on monitor.py output — needs ~30+ posts.
- **Post for Me API gap** for YouTube altered-content flag — would require their team to add the field, OR user accepts the 90-sec/day manual toggle.
- **User decision on Whisper captions** — only major code lever left, ~3 hrs of work, proven impact on TikTok retention. They've signaled "monitoring and iteration is important" so this is paused pending data.
