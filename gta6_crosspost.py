"""Post approved GTA6 clips to the exact existing Instagram/YouTube destinations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import requests
from archive_recovery_check import quota_evidence

BASE = 'https://api.postforme.dev/v1'
DESTINATIONS = {
    'instagram': {'id': 'spc_gu1jpig48SRDfABsgU24', 'user_id': '17841433845153049', 'username': 'gtaviclipfix'},
    'youtube': {'id': 'spc_XzVCHOliiqyX9TJ6FMWfr', 'user_id': 'UCdL4ljG4SqfEA8qk5yd6v5w'},
}

def api(method, path, **kwargs):
    r = requests.request(method, BASE + path, headers={'Authorization': 'Bearer ' + os.environ['POSTFORME_API_KEY']}, timeout=60, **kwargs)
    if not r.ok:
        raise RuntimeError(f'Posting service HTTP {r.status_code}; no raw diagnostics exported')
    return r.json()

def validate_account(platform, data):
    expected = DESTINATIONS[platform]
    if (data.get('id') != expected['id'] or data.get('platform') != platform
            or str(data.get('user_id')) != expected['user_id']):
        raise ValueError(f'{platform}: exact account identity mismatch')
    if expected.get('username') and data.get('username') != expected['username']:
        raise ValueError(f'{platform}: username mismatch')
    return {k: data.get(k) for k in ('id', 'platform', 'user_id', 'username', 'status')}

def inspect():
    result = {}
    for platform, expected in DESTINATIONS.items():
        result[platform] = validate_account(platform, api('GET', '/social-accounts/' + expected['id']))
    print(json.dumps(result, indent=2))
    Path('gta6-output').mkdir(exist_ok=True)
    Path('gta6-output/accounts.json').write_text(json.dumps(result, indent=2))
    return result

def gh(method, endpoint, **kwargs):
    r = requests.request(method, 'https://api.github.com/repos/' + os.environ['GITHUB_REPOSITORY'] + '/' + endpoint,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'}, timeout=60, **kwargs)
    if not r.ok:
        raise RuntimeError(f'GitHub ledger HTTP {r.status_code}')
    return r.json()

def reservation(clip_id):
    title = '[gta6-crosspost] ' + clip_id
    for page in range(1, 101):
        rows = gh('GET', 'issues', params={'state': 'all', 'per_page': 100, 'page': page})
        found = [r for r in rows if r['title'] == title and not r.get('pull_request')]
        if found:
            return found[0]
        if len(rows) < 100:
            return None
    raise ValueError('Incomplete publication ledger; stopping')

def validate_clip(clip):
    if not re.fullmatch(r'\d{15,25}', clip['id']):
        raise ValueError('Invalid video ID')
    if not re.fullmatch(r'https://www\.tiktok\.com/@[A-Za-z0-9_.]+/video/' + clip['id'], clip['source']):
        raise ValueError('Source must be an exact approved TikTok video URL')
    if not re.fullmatch(r'[a-f0-9]{64}', clip['sha256']) or not clip.get('caption') or not clip.get('title'):
        raise ValueError('Missing approved media fingerprint or metadata')

def payload(clip, media_url):
    return {'external_id': 'gta6-' + clip['id'], 'caption': clip['caption'],
        'social_accounts': [d['id'] for d in DESTINATIONS.values()], 'media': [{'url': media_url}],
        'platform_configurations': {
            'instagram': {'caption': clip['caption'], 'placement': 'reels', 'share_to_feed': True},
            'youtube': {'title': clip['title'][:100], 'description': clip['caption'] + '\nSource: ' + clip['source'],
                'privacy_status': 'public', 'made_for_kids': False, 'contains_synthetic_media': False},
        }}

def status(post_id):
    if not re.fullmatch(r'sp_[A-Za-z0-9]+', post_id):
        raise ValueError('Invalid provider post ID')
    data = api('GET', '/social-post-results', params={'post_id': post_id, 'limit': 100})
    rows = data if isinstance(data, list) else data.get('data', [])
    out = {}
    for platform, expected in DESTINATIONS.items():
        matches = [r for r in rows if r.get('post_id') == post_id and r.get('social_account_id') == expected['id']]
        successful = [r for r in matches if r.get('success') is True]
        if successful:
            out[platform] = {'status': 'provider_success', 'url': (successful[-1].get('platform_data') or {}).get('url')}
        elif matches and all(r.get('success') is False for r in matches):
            out[platform] = {'status': 'failed', 'result_id': matches[-1].get('id'),'quota':quota_evidence(matches[-1].get('error'))}
        else:
            out[platform] = {'status': 'pending'}
    Path('gta6-output').mkdir(exist_ok=True)
    Path('gta6-output/delivery.json').write_text(json.dumps({'post_id':post_id, 'platforms':out}, indent=2))
    print(json.dumps(out, indent=2))
    return out

def publish(clip_id):
    accounts = inspect()
    if any(a['status'] != 'connected' for a in accounts.values()):
        raise ValueError('Destination disconnected; reconnect before publishing')
    catalog = json.loads(Path('gta6/approved_clips.json').read_text())
    clips = [c for c in catalog if c['id'] == clip_id]
    if len(clips) != 1:
        raise ValueError('Clip is not uniquely approved')
    clip = clips[0]
    validate_clip(clip)
    existing = reservation(clip_id)
    if existing:
        print(f"Already reserved in issue #{existing['number']}; no duplicate submitted")
        return
    Path('gta6-output').mkdir(exist_ok=True)
    original = Path('gta6-output/original.mp4')
    subprocess.run(['yt-dlp', '--no-playlist', '-o', str(original), clip['source']], check=True, stdout=subprocess.DEVNULL)
    if hashlib.sha256(original.read_bytes()).hexdigest() != clip['sha256']:
        raise ValueError('Source media changed since local review; no publication')
    media = Path('gta6-output/clip.mp4')
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(original), '-c:v', 'libx264', '-preset', 'fast',
        '-crf', '21', '-c:a', 'aac', '-movflags', '+faststart', '-y', str(media)], check=True)
    issue = gh('POST', 'issues', json={'title': '[gta6-crosspost] ' + clip_id,
        'body': 'Reserved before upload. Instagram @gtaviclipfix and YouTube UCdL4ljG4SqfEA8qk5yd6v5w only.\nSource: ' + clip['source'] + '\nCheck provider before retrying; closing this issue does not release the reservation.'})
    upload = api('POST', '/media/create-upload-url')
    if not all(str(upload.get(k, '')).startswith('https://') for k in ('upload_url', 'media_url')):
        raise ValueError('Invalid media upload response; reservation retained')
    with media.open('rb') as f:
        r = requests.put(upload['upload_url'], data=f, headers={'Content-Type': 'video/mp4'}, timeout=300)
    if not r.ok:
        raise RuntimeError('Media upload failed; reservation retained')
    result = api('POST', '/social-posts', json=payload(clip, upload['media_url']))
    post_id = result.get('id')
    if not post_id:
        raise ValueError('Uncertain provider result; inspect reservation before retry')
    body = f"Accepted by provider, not yet confirmed published.\nPost for Me ID: `{post_id}`\nSource: {clip['source']}\nPlatforms: instagram, youtube. TikTok excluded."
    gh('PATCH', f"issues/{issue['number']}", json={'body': body})
    print(f'Accepted: {post_id}; ledger issue #{issue["number"]}')
    for attempt in range(8):
        delivery = status(post_id)
        if all(x['status'] != 'pending' for x in delivery.values()):
            break
        time.sleep(15)
    gh('PATCH', f"issues/{issue['number']}", json={'body':body + '\n\nDelivery:\n```json\n' + json.dumps(delivery, indent=2) + '\n```'})

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['inspect', 'publish', 'status'])
    p.add_argument('--clip-id')
    p.add_argument('--post-id')
    a = p.parse_args()
    try:
        if a.operation == 'inspect': inspect()
        elif a.operation == 'publish': publish(a.clip_id)
        else: status(a.post_id)
    except Exception as e:
        raise SystemExit(f'Stopped: {type(e).__name__}: ' + (str(e) if isinstance(e, (ValueError, RuntimeError)) else 'Inspect the reserved post before retrying; raw diagnostics withheld')) from None
