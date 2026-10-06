"""GET-only capability/duplicate preflight for an explicitly requested failed preparation."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re

import requests
import archive_slots as slots
import archive_autofill as fill
import clipping as clips
from archive_recovery_check import pages


def failed_context(slot_issue, source_issue):
    slot = clips.github('GET', f'issues/{int(slot_issue)}')
    data = slots.record(slot)
    if data['phase'] != 'preparation_failed' or data.get('publishing_run_id') or data.get('clip_id') or data.get('recovery'):
        raise ValueError('Failed slot is consumed, ambiguous or already recovered; hold')
    run = clips.github('GET', 'actions/runs/' + data['owner_run_id'])
    if (run.get('status') != 'completed' or run.get('conclusion') != 'failure'
            or run.get('path') != '.github/workflows/daily-video.yml' or run.get('head_branch') != 'main'
            or str(run.get('run_attempt')) != data['owner_attempt']):
        raise ValueError('Original owner is not a terminal failed main preparation')
    jobs = clips.github('GET', 'actions/runs/' + data['owner_run_id'] + '/jobs')
    failures = [s['name'] for j in jobs['jobs'] for s in j.get('steps', []) if s.get('conclusion') == 'failure']
    if failures != ['Build the next archival story']:
        raise ValueError('Original failure stage is not exclusive preparation')
    source = clips.github('GET', f'issues/{int(source_issue)}')
    body = source.get('body') or ''
    match = re.fullmatch(r'Source: https://archive.org/details/([a-zA-Z0-9_-]+)\nModel: ([a-zA-Z0-9_.-]+)\nAutomated editorial check passed.\nSCRIPT:\n(.+)', body, re.S)
    if (not match or source.get('user', {}).get('login') != 'github-actions[bot]'
            or source['title'] != '[archive-source] ' + fill.source_key(match[1])
            or not clips.timestamp(run['created_at']) <= clips.timestamp(source['created_at']) <= clips.timestamp(run['updated_at'])):
        raise ValueError('Source is not the original passed bot preparation')
    if any(i['title'] == '[clip-publication] ' + fill.source_key(match[1]) for i in slots.issues()):
        raise ValueError('Publication reservation exists; reconcile without regeneration')
    return data, run, match[1], match[3]


def history_matches(items, voice, text, run):
    lower, upper = clips.timestamp(run['created_at']).timestamp(), clips.timestamp(run['updated_at']).timestamp()
    return [x for x in items if x.get('voice_id') == voice and x.get('text') == text
            and x.get('model_id') == 'eleven_multilingual_v2' and x.get('source') == 'TTS'
            and isinstance(x.get('date_unix'), (int, float)) and lower <= x['date_unix'] <= upper]


def exact_alignment(item, text):
    def candidates(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from candidates(child)
    for value in candidates(item.get('alignments')):
        if value.get('characters') != list(text):
            continue
        starts, ends = value.get('character_start_times_seconds'), value.get('character_end_times_seconds')
        if not isinstance(starts, list) or not isinstance(ends, list) or len(starts) != len(text) or len(ends) != len(text):
            continue
        if all(isinstance(a, (int, float)) and not isinstance(a, bool) and isinstance(b, (int, float)) and not isinstance(b, bool)
               and math.isfinite(a) and math.isfinite(b) and 0 <= a <= b and (not n or a >= starts[n-1])
               for n, (a, b) in enumerate(zip(starts, ends))):
            return {'starts': starts, 'ends': ends}
    return None


def inspect(slot_issue, source_issue, output):
    data, run, archive_id, text = failed_context(slot_issue, source_issue)
    key = fill.source_key(archive_id)
    accounts = json.loads(os.environ['CLIP_DESTINATIONS_JSON'])
    if set(accounts) != {'youtube', 'instagram', 'tiktok'}:
        raise ValueError('Configured platform set changed; hold')
    for platform, account_id in accounts.items():
        account = clips.api_json('GET', 'https://api.postforme.dev/v1/social-accounts/' + clips.identifier(account_id), os.environ['POSTFORME_API_KEY'])
        if account.get('id') != account_id or account.get('platform') != platform or account.get('status') != 'connected':
            raise ValueError('Existing configured destination is not connected; hold')
    external = 'creator-clip-' + key
    existing = [x for x in pages('social-posts', external_id=external) if x.get('external_id') == external]
    report = {'read_only': True, 'slot_issue': int(slot_issue), 'source_issue': int(source_issue), 'slot': data['slot'],
              'original_run': data['owner_run_id'], 'source_id': key, 'script_digest': clips.digest(text),
              'existing_provider_post_ids': [x['id'] for x in existing], 'narration_history': 'not checked',
              'action': 'hold; no paid generation, lock mutation or post'}
    if existing:
        report['blocker'] = 'Provider request exists; accepted/pending/ambiguous results cannot be regenerated'
    else:
        voice = clips.identifier(os.environ['ELEVENLABS_VOICE_ID'])
        headers = {'xi-api-key': os.environ['ELEVENLABS_API_KEY']}
        response = requests.get('https://api.elevenlabs.io/v1/history', headers=headers,
                                params={'voice_id': voice, 'page_size': 100, 'source': 'TTS', 'model_id': 'eleven_multilingual_v2',
                                        'date_after_unix': int(clips.timestamp(run['created_at']).timestamp()),
                                        'date_before_unix': int(clips.timestamp(run['updated_at']).timestamp()) + 1}, timeout=45)
        if not response.ok:
            report['narration_history'] = f'Existing history read unavailable: HTTP {response.status_code}'
        else:
            payload = response.json(); items = payload.get('history', [])
            matches = history_matches(items, voice, text, run)
            report['narration_history_matches'] = len(matches)
            report['history_read_complete'] = not payload.get('has_more', False)
            if len(matches) != 1 or payload.get('has_more', False):
                report['narration_history'] = 'Exact unique history item not proved within bounded read'
            else:
                item_id = clips.identifier(matches[0]['history_item_id'])
                detail = requests.get('https://api.elevenlabs.io/v1/history/' + item_id, headers=headers, timeout=45)
                item = detail.json() if detail.ok else {}
                exact = history_matches([item], voice, text, run) == [item] and item.get('history_item_id') == item_id
                alignment = exact_alignment(item, text) if exact else None
                report['narration_history'] = 'Exact narration and alignment available' if alignment else 'Exact character alignment unavailable'
                report['alignment_available'] = bool(alignment)
                report['history_item_digest'] = clips.digest(item_id)
                if alignment:
                    audio = requests.get('https://api.elevenlabs.io/v1/history/' + item_id + '/audio',
                                         headers=headers, timeout=45, stream=True)
                    if audio.ok and audio.headers.get('content-type', '').split(';')[0] in ('audio/mpeg', 'audio/mp3'):
                        fingerprint, total = hashlib.sha256(), 0
                        for chunk in audio.iter_content(65536):
                            total += len(chunk)
                            if total > 10 * 1024**2:
                                raise ValueError('Historical narration exceeds bounded read; hold')
                            fingerprint.update(chunk)
                        report['audio_available'] = total > 0
                        if total:
                            report['audio_sha256'] = fingerprint.hexdigest()
                    else:
                        report['audio_available'] = False
                # Private historical text, timestamps, audio and account payloads stay in memory.
    Path(output).mkdir(parents=True, exist_ok=True)
    (Path(output) / 'preparation-recovery-check.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot-issue', required=True, type=int)
    parser.add_argument('--source-issue', required=True, type=int)
    parser.add_argument('--output', default='recovery-output')
    args = parser.parse_args()
    inspect(args.slot_issue, args.source_issue, args.output)
