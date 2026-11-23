# Independent hourly cloud timer

Prepared and tested; not deployed until the user approves the repository-limited GitHub credential.

This Cloudflare Worker invokes only `tick` on `gta6-hourly.yml` in the existing GitHub repository. It runs a cheap check every five minutes during 7 a.m.–7:59 p.m. America/Dawson_Creek. GitHub's ledger still permits one publication per hour from 8 a.m.–7 p.m., maximum 12/day, and two discovery windows. No social-account credentials are stored in this Worker. HTTP requests return 404; only scheduled events dispatch jobs.

Deploy through the existing Wrangler OAuth account after explicit approval to store a fine-grained GitHub token scoped to Actions (read/write) on `energeticcity/youtube-political-pipeline`. Store it as Worker secret `GITHUB_DISPATCH_TOKEN`, with a one-year expiration. Do not upload the broader local GitHub CLI token. The global GTA6 publishing switch also applies to `tick` dispatches.

Run `node --test worker.test.mjs` and `wrangler deploy --dry-run` before deployment. Keep inherited Cloudflare API-token environment variables unset when using the existing Workers OAuth account. Deploy without enabling a paid plan; usage is fewer than 300 invocations/day, within Cloudflare's free Workers request allowance. After deployment, verify an actual Cron event and its corresponding GitHub run; a manual dispatch is not timer evidence.

A YouTube `uploadLimitExceeded` result is a channel-wide daily limit. The publisher records a 24-hour hold for YouTube while keeping TikTok and Instagram eligible. Further delivery depends on the channel limit clearing or the owner obtaining higher feature access.
