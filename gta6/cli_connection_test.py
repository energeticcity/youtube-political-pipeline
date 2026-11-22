"""Manual integration tests for upstream CLIs; never used by the posting schedule.

Only sanitized results leave the runner. TikTok/YouTube tests request private
visibility. Instagram checks login only: the upstream CLI has no draft switch.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import unquote

import requests

PLATFORM = sys.argv[1]
OUT = Path('cli-test-results')
OUT.mkdir(exist_ok=True)
RESULT = {'platform': PLATFORM, 'test': 'upstream-cli', 'public_uploads': False}


def save():
    text = json.dumps(RESULT, indent=2)
    (OUT / f'{PLATFORM}.json').write_text(text)
    print(text, flush=True)


def command(args, *, cwd=None, timeout=180):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                       stdin=subprocess.DEVNULL)
    if p.returncode:
        diagnostic = p.stdout + p.stderr
        # Upstream errors can carry request URLs or session material. Redact the
        # supplied credentials (including every nested cookie value) before
        # retaining a short diagnostic in the integration-test artifact.
        def redact_value(value):
            nonlocal diagnostic
            if isinstance(value, dict):
                for item in value.values():
                    redact_value(item)
            elif isinstance(value, list):
                for item in value:
                    redact_value(item)
            elif isinstance(value, str) and len(value) >= 4:
                diagnostic = diagnostic.replace(value, '[redacted]')
        for name, value in os.environ.items():
            if value and any(word in name for word in ['TOKEN', 'SECRET', 'SESSION', 'API_KEY', 'PASSWORD']):
                redact_value(value)
                try:
                    redact_value(json.loads(value))
                except ValueError:
                    pass
        diagnostic = re.sub(r'https?://\S+', '[URL removed]', diagnostic)
        diagnostic = re.sub(r'[A-Za-z0-9_%+=/.-]{32,}', '[long value removed]', diagnostic)
        RESULT['failed_command'] = Path(args[0]).name
        RESULT['diagnostic_excerpt'] = diagnostic[-1000:]
        known = ['invalid_grant', 'login_required', 'checkpoint_required',
                 'challenge_required', 'ModuleNotFoundError', 'ImportError',
                 'Executable doesn\'t exist', 'TimeoutError', 'invalid',
                 'insufficientPermissions', 'uploadLimitExceeded', 'quotaExceeded']
        RESULT['cli_exit_code'] = p.returncode
        RESULT['diagnostic_categories'] = [s for s in known if s in diagnostic]
        raise RuntimeError('upstream_cli_failed')
    return p.stdout


def fixture():
    path = Path(tempfile.gettempdir()) / f'gta6-cli-test-{PLATFORM}.mp4'
    command(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
             '-f', 'lavfi', '-i', 'color=c=0x172039:s=720x1280:r=25:d=6',
             '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo',
             '-t', '6', '-c:v', 'libx264', '-preset', 'fast', '-pix_fmt', 'yuv420p',
             '-c:a', 'aac', '-movflags', '+faststart', str(path)])
    return str(path)


def tiktok():
    from autotok import Account, Client
    command(['autotok', 'upload', '--help'])
    RESULT['cli_help'] = 'passed'
    account = Account.from_dict(json.loads(os.environ['GTA6_TIKTOK_SESSION']))
    if account.name != 'gta6_clips':
        raise RuntimeError('unexpected_saved_account')
    response = Client(account)._session().get(
        'https://www.tiktok.com/passport/web/account/info/', params={'aid': 1988}, timeout=45)
    response.raise_for_status()
    data = response.json().get('data', {})
    if data.get('username') != 'gtaviclipfix' or str(data.get('user_id')) != '7630582867722372104':
        raise RuntimeError('unexpected_tiktok_identity')
    RESULT['account'] = '@gtaviclipfix'
    path = Path.home() / '.autotok/accounts/gta6_clips.json'
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(account.to_dict()))
    path.chmod(0o600)
    command(['autotok', 'accounts', 'check', 'gta6_clips'])
    RESULT['authenticated_check'] = 'passed'
    RESULT['upload'] = 'starting_private_test'
    save()
    output = command(['autotok', 'upload', '-u', 'gta6_clips', '-v', fixture(),
                      '-t', 'Private uploader connection test', '-vi', '1',
                      '-ct', '0', '-d', '0', '-st', '0'], timeout=360)
    match = re.search(r'Video id:\s*([A-Za-z0-9_-]+)', output)
    if not match:
        raise RuntimeError('upload_receipt_not_found_do_not_retry_blindly')
    RESULT.update(upload='accepted_private_test', upstream_video_reference=match.group(1),
                  requested_visibility='private')


def youtube():
    from oauth2client.client import GoogleCredentials
    command(['youtube-upload', '--help'])
    RESULT['cli_help'] = 'passed'
    values = {key: os.environ.get('YOUTUBE_' + key, '')
              for key in ['CLIENT_ID', 'CLIENT_SECRET', 'REFRESH_TOKEN']}
    if not all(values.values()):
        raise RuntimeError('youtube_credentials_missing')
    r = requests.post('https://oauth2.googleapis.com/token', data={
        'client_id': values['CLIENT_ID'], 'client_secret': values['CLIENT_SECRET'],
        'refresh_token': values['REFRESH_TOKEN'], 'grant_type': 'refresh_token'}, timeout=45)
    if not r.ok:
        RESULT['oauth_error'] = r.json().get('error', 'unknown')
        RESULT['http_status'] = r.status_code
        raise RuntimeError('youtube_token_refresh_failed')
    token = r.json()['access_token']
    r = requests.get('https://www.googleapis.com/youtube/v3/channels',
                     params={'part': 'id,snippet', 'mine': 'true'},
                     headers={'Authorization': 'Bearer ' + token}, timeout=45)
    if not r.ok:
        RESULT['http_status'] = r.status_code
        raise RuntimeError('youtube_channel_lookup_failed')
    ids = [x['id'] for x in r.json().get('items', [])]
    if ids != ['UCdL4ljG4SqfEA8qk5yd6v5w']:
        raise RuntimeError('unexpected_youtube_channel')
    RESULT.update(account='@dadjokefix', channel_id=ids[0], authenticated_check='passed')
    with tempfile.TemporaryDirectory() as tmp:
        credentials = Path(tmp) / 'credentials.json'
        secrets = Path(tmp) / 'client-secrets.json'
        cred = GoogleCredentials(token, values['CLIENT_ID'], values['CLIENT_SECRET'],
                                 values['REFRESH_TOKEN'], None,
                                 'https://oauth2.googleapis.com/token', 'gta6-cli-test')
        credentials.write_text(cred.to_json())
        secrets.write_text(json.dumps({'installed': {
            'client_id': values['CLIENT_ID'], 'client_secret': values['CLIENT_SECRET'],
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'redirect_uris': ['http://localhost']}}))
        credentials.chmod(0o600)
        secrets.chmod(0o600)
        RESULT['upload'] = 'starting_private_test'
        save()
        output = command(['youtube-upload', '--client-secrets', str(secrets),
                          '--credentials-file', str(credentials), '--privacy', 'private',
                          '--title', 'Private uploader connection test', fixture()], timeout=360)
        ids = re.findall(r'^[A-Za-z0-9_-]{11}$', output, re.M)
        if len(ids) != 1:
            raise RuntimeError('upload_receipt_not_found_do_not_retry_blindly')
        video_id = ids[0]
        r = requests.get('https://www.googleapis.com/youtube/v3/videos',
                         params={'part': 'status,snippet', 'id': video_id},
                         headers={'Authorization': 'Bearer ' + token}, timeout=45)
        r.raise_for_status()
        item = r.json()['items'][0]
        if item['snippet']['channelId'] != RESULT['channel_id'] or item['status']['privacyStatus'] != 'private':
            raise RuntimeError('youtube_upload_identity_or_privacy_mismatch')
        RESULT.update(upload='verified_private_test', video_id=video_id, verified_visibility='private')


def instagram():
    repo = Path(os.environ['SAU_REPO'])
    command(['sau', 'instagram', '--help'], cwd=repo)
    RESULT['cli_help'] = 'passed'
    raw = os.environ.get('IG_SESSION', '').strip()
    if not raw:
        raise RuntimeError('instagram_session_missing')
    try:
        stored = json.loads(raw)
    except ValueError:
        stored = None
    if isinstance(stored, dict) and isinstance(stored.get('cookies'), list):
        state = {'cookies': stored['cookies'], 'origins': stored.get('origins', [])}
    else:
        values = stored.get('cookies', stored) if isinstance(stored, dict) else {'sessionid': raw}
        if not isinstance(values, dict) or not values.get('sessionid'):
            raise RuntimeError('instagram_session_format_needs_browser_login')
        uid = values.get('ds_user_id') or unquote(values['sessionid']).split(':')[0]
        if not str(uid).isdigit():
            raise RuntimeError('instagram_session_format_needs_browser_login')
        values['ds_user_id'] = str(uid)
        state = {'cookies': [{'name': name, 'value': str(value), 'domain': '.instagram.com',
                              'path': '/', 'secure': True, 'httpOnly': name == 'sessionid',
                              'sameSite': 'Lax'} for name, value in values.items()
                             if name in {'sessionid', 'ds_user_id', 'csrftoken', 'mid', 'ig_did'}],
                 'origins': []}
    cookies = {c['name']: c['value'] for c in state['cookies']}
    response = requests.get('https://www.instagram.com/api/v1/accounts/current_user/',
                            params={'edit': 'true'}, cookies=cookies,
                            headers={'X-IG-App-ID': '936619743392459'}, timeout=45)
    try:
        username = response.json().get('user', {}).get('username')
    except ValueError:
        username = None
    if username and username != 'dadjokefix':
        raise RuntimeError('unexpected_instagram_identity')
    path = repo / 'cookies/instagram_dadjokefix.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))
    path.chmod(0o600)
    RESULT['session_identity_lookup'] = 'matched' if username else 'not_confirmed'
    save()
    command(['sau', 'instagram', 'check', '--account', 'dadjokefix'], cwd=repo, timeout=210)
    if username != 'dadjokefix':
        raise RuntimeError('instagram_login_valid_but_target_username_unconfirmed')
    RESULT.update(account='@dadjokefix', authenticated_check='passed',
                  upload='not_attempted_cli_has_no_unpublished_mode')


try:
    {'tiktok': tiktok, 'youtube': youtube, 'instagram': instagram}[PLATFORM]()
    RESULT['status'] = 'passed'
except Exception as exc:
    RESULT['status'] = 'failed'
    # Only our fixed identifiers are safe to include; upstream exceptions may contain tokens.
    message = str(exc)
    RESULT['failure'] = message if re.fullmatch(r'[a-z_]+', message) else type(exc).__name__
    save()
    raise SystemExit(1)
save()
