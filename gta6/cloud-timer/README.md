# Independent hourly cloud timer

Deployed to the existing Cloudflare account on November 23, 2026. The approved repository-limited credential is stored as a Worker secret and expires November 23, 2027. Automatic Cron verification passed: a real 1:57 p.m. check was followed by the 2:02 p.m. cloud-only publication run. TikTok and Instagram videos were verified on their public pages.

This Cloudflare Worker invokes only `tick` on `gta6-hourly.yml` in the existing GitHub repository. It runs a cheap check every five minutes during 7 a.m.–7:59 p.m. America/Dawson_Creek. GitHub's ledger still permits one publication per hour from 8 a.m.–7 p.m., maximum 12/day, and two discovery windows. No social-account credentials are stored in this Worker. HTTP requests return 404; only scheduled events dispatch jobs.

Deploy through the existing Wrangler OAuth account after explicit approval to store a fine-grained GitHub token scoped to Actions (read/write) on `energeticcity/youtube-political-pipeline`. Store it as Worker secret `GITHUB_DISPATCH_TOKEN`, with a one-year expiration. Do not upload the broader local GitHub CLI token. The global GTA6 publishing switch also applies to `tick` dispatches.

Run `node --test worker.test.mjs` and `wrangler deploy --dry-run` before deployment. Keep inherited Cloudflare API-token environment variables unset when using the existing Workers OAuth account. Deploy without enabling a paid plan; usage is fewer than 300 invocations/day, within Cloudflare's free Workers request allowance. After deployment, verify an actual Cron event and its corresponding GitHub run; a manual dispatch is not timer evidence.

A YouTube `uploadLimitExceeded` result is a channel-wide daily limit. The publisher records a 24-hour hold for YouTube while keeping TikTok and Instagram eligible. Further delivery depends on the channel limit clearing or the owner obtaining higher feature access.

A temporary Mac LaunchAgent (`com.gta6cloud.dispatch`) was installed and verified as a fallback during setup. It remains unloaded and disabled after confirming the independent cloud publication. The Mac backup uses the existing GitHub Keychain authentication and never transfers the broad local GitHub token. It is not required for Cloudflare operation.

## Verified November 23, 2026

The authoritative clock is Cloudflare. It starts GitHub runs through the dispatch API, so the GitHub event type is `workflow_dispatch` and the run name contains `(cloudflare)`. Do not filter status checks to GitHub's native `schedule` events: that would omit the working cloud timer. Native GitHub schedules remain as a redundant check and share the same durable hourly reservations.

- Automatic clock check: https://github.com/energeticcity/youtube-political-pipeline/actions/runs/45264650909 (1:57 p.m. Dawson Creek; existing slot skipped).
- Automatic publication: https://github.com/energeticcity/youtube-political-pipeline/actions/runs/45265510620 (2:02 p.m.; record #296).
- Public TikTok proof: https://www.tiktok.com/@gtaviclipfix/video/7711475080701693185
- Public Instagram proof: https://www.instagram.com/reel/DgGTZiDPfjS/
- YouTube: channel daily upload limit; hold recorded in queue #266 until November 24, 2026 at 12:14 p.m. Dawson Creek. Check per-platform receipts; a successful job can contain an intentional YouTube hold.

The limited Worker credential has Actions read/write and mandatory Metadata read access on this one repository, no account permissions, and expires November 23, 2027. The temporary local transfer file was deleted. The temporary Mac clock is unloaded and disabled; Cloudflare needs no open browser, Mac, or Codex session.
