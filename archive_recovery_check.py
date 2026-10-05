"""Read-only YouTube recovery evidence. Every provider request is GET."""
import argparse
import json
import os
from pathlib import Path
import re

import clipping

BASE = 'https://api.postforme.dev/v1'


def pages(endpoint, **filters):
    rows = []
    for offset in range(0, 2000, 100):
        payload = clipping.api_json('GET', f'{BASE}/{endpoint}', os.environ['POSTFORME_API_KEY'],
                                    params={**filters, 'limit': 100, 'offset': offset})
        batch = payload if isinstance(payload, list) else payload.get('data', [])
        rows.extend(batch)
        if len(batch) < 100:
            return rows
    raise ValueError('Provider pagination limit reached; evidence incomplete, hold recovery')


def quota_evidence(error):
    # Inspect only error messages; never transport config, headers or full payloads.
    messages = []

    def visit(value, depth=0):
        if depth > 8:
            return
        if isinstance(value, str):
            try:
                visit(json.loads(value), depth + 1)
            except (ValueError, TypeError):
                messages.append(value)
        elif isinstance(value, dict):
            for key, child in value.items():
                if key in ('message', 'error', 'errors', 'reason', 'status'):
                    visit(child, depth + 1)
        elif isinstance(value, list):
            for child in value[:20]:
                visit(child, depth + 1)

    visit(error)
    text = '\n'.join(messages)
    evidence = {'classification': 'unclassified; hold recovery'}
    if all(label in text for label in ('Video Uploads per day', 'project_number:', 'youtube.googleapis.com')):
        evidence['classification'] = 'youtube_api_project_daily_upload_quota'
        evidence['quota_metric'] = 'Video Uploads'
        evidence['quota_limit'] = 'Video Uploads per day'
        evidence['service'] = 'youtube.googleapis.com'
        project = re.search(r'project_number:(\d+)', text)
        if project:
            evidence['consumer'] = 'project_number:' + project[1]
    for label in ('rateLimitExceeded', 'RESOURCE_EXHAUSTED', 'uploadLimitExceeded'):
        if label in text:
            evidence[label] = True
    if re.search(r'\b429\b', text):
        evidence['http_status'] = 429
    if 'Failed to start YouTube resumable upload session' in text:
        evidence['failure_stage'] = 'before_resumable_upload_session'
    return evidence


def inspect(post_id, output):
    clipping.identifier(post_id)
    accounts = json.loads(os.environ['CLIP_DESTINATIONS_JSON'])
    account_id = clipping.identifier(accounts['youtube'])
    original = clipping.api_json('GET', f'{BASE}/social-posts/{post_id}', os.environ['POSTFORME_API_KEY'])
    if original.get('id') != post_id:
        raise ValueError('Original post identity mismatch; hold recovery')
    ids = [a['id'] if isinstance(a, dict) else a for a in original.get('social_accounts', [])]
    if account_id not in ids:
        raise ValueError('Original post does not include configured YouTube account; hold recovery')
    external = clipping.identifier(original.get('external_id'))
    if not external.startswith('creator-clip-'):
        raise ValueError('Post is not a checked archive submission; hold recovery')
    account = clipping.api_json('GET', f'{BASE}/social-accounts/{account_id}', os.environ['POSTFORME_API_KEY'])
    results = [r for r in pages('social-post-results', post_id=post_id, social_account_id=account_id)
               if r.get('post_id') == post_id and r.get('social_account_id') == account_id]
    summaries = []
    for row in results:
        platform = row.get('platform_data') or {}
        summaries.append({'result_id': row.get('id'), 'success': row.get('success'),
                          'has_platform_video_reference': bool(platform.get('id') or platform.get('url')),
                          'quota': quota_evidence(row.get('error'))})
    retry_reference = clipping.identifier(post_id + '-youtube-retry-1')
    originals = pages('social-posts', external_id=external)
    recoveries = pages('social-posts', external_id=retry_reference)
    report = {'read_only': True, 'post_id': post_id, 'original_status': original.get('status'),
              'original_external_id': external,
              'youtube_account': {k: account.get(k) for k in ('id', 'platform', 'username', 'user_id', 'status')},
              'youtube_results': summaries,
              'same_reference_post_ids': [p['id'] for p in originals if p.get('external_id') == external],
              'recovery_reference': retry_reference,
              'recovery_post_ids': [p['id'] for p in recoveries if p.get('external_id') == retry_reference],
              'action': 'hold; no post or retry submitted',
              'remaining_checks': ['Provider quota capacity and post billing/cadence allowance',
                                   'All durable publication/recovery locks including closed issues',
                                   'No prior dashboard/manual recovery or channel duplicate',
                                   'Fresh source rights, trusted preview and video fingerprint',
                                   'Master publishing switches and connected destination identity']}
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'recovery-check.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--post-id', required=True)
    parser.add_argument('--output', default='delivery-output')
    args = parser.parse_args()
    try:
        inspect(args.post_id, args.output)
    except Exception as error:
        raise SystemExit(f'Read-only recovery check stopped: {type(error).__name__}; hold recovery.')
