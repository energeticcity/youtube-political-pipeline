"""Explicit, single-destination retry of a confirmed failed Instagram post."""
import argparse
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

import clipping
import archive_pipeline


def payload_for_retry(original, account_id):
    ids = [a['id'] if isinstance(a, dict) else a for a in original['social_accounts']]
    if account_id not in ids or len(original.get('media') or []) != 1:
        raise ValueError('Original post does not match the Instagram destination/single video')
    url = original['media'][0]['url']
    clipping.public_https(url)
    config = (original.get('platform_configurations') or {}).get('instagram') or {
        'placement': 'reels', 'share_to_feed': True}
    return {'caption': original['caption'], 'social_accounts': [account_id],
            'media': [{'url': url}], 'platform_configurations': {'instagram': config}}


def retry(post_id):
    clipping.identifier(post_id)
    account_id = json.loads(os.environ['CLIP_PAUSED_DESTINATIONS_JSON'])['instagram']
    clipping.identifier(account_id)
    key, base = os.environ['POSTFORME_API_KEY'], 'https://api.postforme.dev/v1'
    original = clipping.api_json('GET', f'{base}/social-posts/{post_id}', key)
    data = clipping.api_json('GET', f'{base}/social-post-results', key,
        params={'post_id': post_id, 'social_account_id': account_id, 'limit': 100})
    rows = data if isinstance(data, list) else data.get('data', [])
    rows = [r for r in rows if r.get('post_id') == post_id and r.get('social_account_id') == account_id]
    if not rows or any(r.get('success') is not False for r in rows):
        raise ValueError('Instagram is not confirmed failed; refusing a possible duplicate')
    account = clipping.api_json('GET', f'{base}/social-accounts/{account_id}', key)
    if account.get('platform') != 'instagram' or account.get('status') != 'connected':
        raise ValueError('Reconnect Instagram before retrying')
    payload = payload_for_retry(original, account_id)
    retry_id = f'{post_id}-instagram-retry-1'
    if clipping.reserved(retry_id):
        raise ValueError('This retry is already reserved; inspect its issue instead of reposting')
    issue = clipping.github('POST', 'issues', json={'title': f'[clip-publication] {retry_id}',
        'body': f'User-authorized Instagram-only retry of {post_id}. Reserved before submission. Do not retry blindly.'})
    payload['external_id'] = retry_id
    post = clipping.api_json('POST', f'{base}/social-posts', key, json=payload)
    if not post.get('id'):
        raise ValueError('Provider response ambiguous; reservation retained')
    clipping.identifier(post['id'])
    clipping.github('PATCH', f"issues/{issue['number']}", json={'body':
        f"Instagram-only retry queued. Post for Me ID: `{post['id']}`. Original: `{post_id}`. YouTube/TikTok excluded."})
    print(f"Instagram-only retry queued: {post['id']}; issue #{issue['number']}")
    os.environ['CLIP_DESTINATIONS_JSON'] = json.dumps({'instagram': account_id})
    args = SimpleNamespace(post_id=post['id'], output='delivery-output')
    for attempt in range(7):
        archive_pipeline.delivery(args)
        result = json.loads(Path('delivery-output/delivery.json').read_text())
        if result['instagram']['status'] != 'pending':
            clipping.github('POST', f"issues/{issue['number']}/comments", json={'body':
                'Delivery result:\n```json\n' + json.dumps(result, indent=2) + '\n```'})
            return
        if attempt < 6:
            time.sleep(15)
    print('Still processing; use the read-only delivery check. Do not submit another retry.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--post-id', required=True)
    try:
        retry(parser.parse_args().post_id)
    except (ValueError, RuntimeError) as error:
        raise SystemExit(str(error))
    except Exception as error:
        raise SystemExit(f'Retry stopped: {type(error).__name__}; check reservation before another attempt.')
