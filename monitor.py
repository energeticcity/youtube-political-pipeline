#!/usr/bin/env python3
"""
Weekly performance digest.

Reads metrics_log.json (per-post metadata we logged at render time) and
pulls the latest view/like/comment counts from Post for Me's
/v1/social-account-feeds endpoint. Joins the two, calculates which
segments / hooks / CTAs / hashtag sets / topics performed best in the
last 7 days, and creates a GitHub Issue with the findings.

Triggered weekly by .github/workflows/weekly-digest.yml.
"""

import os
import sys
import json
import base64
from collections import defaultdict
from datetime import datetime, timezone, timedelta

import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "energeticcity/youtube-political-pipeline")
POSTFORME_API_KEY = os.environ.get("POSTFORME_API_KEY", "")


def log(msg: str):
    print(f"[monitor] {msg}", flush=True)


def read_metrics_log() -> list:
    """Pull the per-post metadata log from the repo."""
    if not GITHUB_TOKEN:
        return []
    resp = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/metrics_log.json",
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        return []
    try:
        return json.loads(base64.b64decode(resp.json()["content"]).decode("utf-8"))
    except Exception:
        return []


def fetch_postforme_feed(account_id: str, limit: int = 100) -> list:
    """Pull a paginated feed for one connected social account WITH metrics."""
    items = []
    cursor = None
    while True:
        params = {"limit": min(limit - len(items), 50), "expand": "metrics"}
        if cursor:
            params["cursor"] = cursor
        resp = requests.get(
            f"https://api.postforme.dev/v1/social-account-feeds/{account_id}",
            headers={"Authorization": f"Bearer {POSTFORME_API_KEY}"},
            params=params,
            timeout=30,
        )
        if resp.status_code != 200:
            log(f"  Feed fetch error {resp.status_code}: {resp.text[:200]}")
            break
        body = resp.json()
        page = body.get("data") or body.get("items") or []
        items.extend(page)
        cursor = body.get("next_cursor") or body.get("cursor")
        if not cursor or len(items) >= limit:
            break
    return items


def list_social_accounts() -> dict:
    """Return {platform: account_id}."""
    resp = requests.get(
        "https://api.postforme.dev/v1/social-accounts",
        headers={"Authorization": f"Bearer {POSTFORME_API_KEY}"},
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    accounts = body if isinstance(body, list) else (body.get("data") or body.get("items") or [])
    out = {}
    for acct in accounts:
        provider = (acct.get("platform") or acct.get("provider") or "").lower()
        if provider:
            out[provider] = acct.get("id") or acct.get("account_id") or ""
    return out


def extract_metrics(feed_item: dict) -> dict:
    """Best-effort extraction across platforms — view/like/comment/share keys
    vary. Returns {views, likes, comments, shares} with 0 defaults."""
    m = feed_item.get("metrics") or {}
    return {
        "views":    int(m.get("views") or m.get("view_count") or m.get("plays") or 0),
        "likes":    int(m.get("likes") or m.get("like_count") or 0),
        "comments": int(m.get("comments") or m.get("comment_count") or 0),
        "shares":   int(m.get("shares") or m.get("share_count") or 0),
    }


def main():
    if not GITHUB_TOKEN or not POSTFORME_API_KEY:
        log("Skipping digest: missing GITHUB_TOKEN or POSTFORME_API_KEY")
        sys.exit(0)

    log("=" * 60)
    log("Weekly performance digest")
    log("=" * 60)

    log_entries = read_metrics_log()
    log(f"  Loaded {len(log_entries)} historical post records")

    # Build map of post_for_me_id → our metadata
    by_pf_id = {e["post_for_me_id"]: e for e in log_entries if e.get("post_for_me_id")}

    cutoff = datetime.now(timezone.utc) - timedelta(days=8)

    # Pull feeds from each connected account
    accounts = list_social_accounts()
    log(f"  Connected platforms: {sorted(accounts.keys())}")

    # Aggregate per-post totals across platforms
    per_post: dict[str, dict] = defaultdict(lambda: {
        "views": 0, "likes": 0, "comments": 0, "shares": 0,
        "platforms": [], "meta": None,
    })

    for platform, acct_id in accounts.items():
        log(f"  Fetching {platform} feed...")
        feed = fetch_postforme_feed(acct_id, limit=80)
        for item in feed:
            pf_id = item.get("post_id") or item.get("social_post_id")
            if not pf_id or pf_id not in by_pf_id:
                continue
            meta = by_pf_id[pf_id]
            try:
                ts = datetime.fromisoformat(meta["timestamp"].replace("Z", "+00:00"))
                if ts < cutoff:
                    continue
            except Exception:
                pass
            metrics = extract_metrics(item)
            per_post[pf_id]["views"]    += metrics["views"]
            per_post[pf_id]["likes"]    += metrics["likes"]
            per_post[pf_id]["comments"] += metrics["comments"]
            per_post[pf_id]["shares"]   += metrics["shares"]
            per_post[pf_id]["platforms"].append(platform)
            per_post[pf_id]["meta"] = meta

    if not per_post:
        log("  No posts with metrics yet — skipping digest")
        return

    log(f"  Joined {len(per_post)} posts with their metadata")

    # Roll up by dimension
    by_segment: dict[str, list] = defaultdict(list)
    by_hook_idx: dict[int, list] = defaultdict(list)
    by_cta: dict[str, list] = defaultdict(list)

    rows = []
    for pf_id, agg in per_post.items():
        meta = agg["meta"]
        rows.append({
            "title": meta.get("title", "?"),
            "episode": meta.get("episode", "?"),
            "views": agg["views"],
            "likes": agg["likes"],
            "comments": agg["comments"],
            "shares": agg["shares"],
            "segment": meta.get("segment_name", ""),
            "cta": meta.get("outro_text", ""),
            "hashtag_idx": meta.get("hashtag_set_index", -1),
            "video_url": meta.get("video_url", ""),
        })
        by_segment[meta.get("segment_name", "")].append(agg["views"])
        by_hook_idx[meta.get("hashtag_set_index", -1)].append(agg["views"])
        by_cta[meta.get("outro_text", "")].append(agg["views"])

    rows.sort(key=lambda r: r["views"], reverse=True)
    top5 = rows[:5]
    bottom5 = rows[-5:] if len(rows) > 5 else []
    total_views = sum(r["views"] for r in rows)
    total_comments = sum(r["comments"] for r in rows)

    def avg(xs): return round(sum(xs) / len(xs)) if xs else 0
    seg_avg = sorted(((s, avg(v), len(v)) for s, v in by_segment.items() if s), key=lambda x: x[1], reverse=True)
    cta_avg = sorted(((c, avg(v), len(v)) for c, v in by_cta.items() if c), key=lambda x: x[1], reverse=True)
    hashtag_avg = sorted(((i, avg(v), len(v)) for i, v in by_hook_idx.items() if i >= 0), key=lambda x: x[1], reverse=True)

    # Build markdown digest
    body = [
        f"## Weekly performance digest — last 7 days",
        f"",
        f"**Posts measured:** {len(rows)} | "
        f"**Total views:** {total_views:,} | "
        f"**Total comments:** {total_comments:,}",
        f"",
        f"### 🏆 Top 5 performers",
        f"| Views | Likes | Comments | Title |",
        f"|---|---|---|---|",
    ]
    for r in top5:
        body.append(f"| {r['views']:,} | {r['likes']:,} | {r['comments']:,} | [#{r['episode']}: {r['title'][:50]}]({r['video_url']}) |")

    if bottom5:
        body += [
            f"",
            f"### 🪦 Bottom 5 performers",
            f"| Views | Likes | Comments | Title |",
            f"|---|---|---|---|",
        ]
        for r in bottom5:
            body.append(f"| {r['views']:,} | {r['likes']:,} | {r['comments']:,} | [#{r['episode']}: {r['title'][:50]}]({r['video_url']}) |")

    if seg_avg:
        body += [f"", f"### 📅 Segment performance (avg views, post count)", f"| Segment | Avg views | # posts |", f"|---|---|---|"]
        for s, a, c in seg_avg:
            body.append(f"| {s} | {a:,} | {c} |")

    if cta_avg:
        body += [f"", f"### 🎯 CTA performance (avg views)", f"| CTA | Avg views | # posts |", f"|---|---|---|"]
        for c, a, n in cta_avg[:7]:
            body.append(f"| {c[:40]} | {a:,} | {n} |")

    if hashtag_avg:
        body += [f"", f"### #️⃣ Hashtag set performance (top 10 by avg views)", f"| Set # | Avg views | # posts |", f"|---|---|---|"]
        for i, a, c in hashtag_avg[:10]:
            body.append(f"| {i} | {a:,} | {c} |")

    body += [
        f"",
        f"---",
        f"",
        f"### What to do with this",
        f"- **Top performers**: copy what worked — segment, CTA, hashtag set, joke topic",
        f"- **Bottom performers**: avoid that combination next week",
        f"- **Best segment**: lean into more of those joke types",
        f"- **Best CTA**: I can pin it as the default and stop rotating if data is clear",
        f"",
        f"_Auto-generated weekly. Tag this issue as wontfix once you've reviewed._",
    ]

    issue_body = "\n".join(body)
    title = f"📊 Weekly digest — {datetime.now(timezone.utc).strftime('%Y-%m-%d')} ({len(rows)} posts, {total_views:,} views)"

    resp = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json={"title": title, "body": issue_body, "labels": ["weekly-digest"]},
        timeout=30,
    )
    resp.raise_for_status()
    log(f"  Issue created: {resp.json().get('html_url', '?')}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"DIGEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
