"""Durable calendar-slot occupancy, serialized by archive-previews/publication."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import uuid

import clipping as clips

CRONS = {f'7 {hour} * * *': hour for hour in (14, 18, 22)}
PREFIX = '[archive-slot] '
VERSION = 1


def utc_now():
    return datetime.now(timezone.utc)


def parse_slot(value):
    slot = clips.timestamp(value)
    if slot.utcoffset() != timedelta(0) or slot.hour not in (14, 18, 22) or (slot.minute, slot.second, slot.microsecond) != (7, 0, 0):
        raise ValueError('Slot must be an existing14:07/18:07/22:07UTC occurrence')
    return slot.astimezone(timezone.utc)


def slot_name(slot):
    return slot.strftime('%Y-%m-%dT%H:%M:00Z')


def resolve(event, cron, requested, created, now):
    created, now = created.astimezone(timezone.utc), now.astimezone(timezone.utc)
    if event == 'schedule':
        if cron not in CRONS:
            return None, 'Legacy or unknown cron has no unambiguous admission identity'
        slot = created.replace(hour=CRONS[cron], minute=7, second=0, microsecond=0)
        # Small early run-creation skew is harmless only once the slot is actually due.
        if not -timedelta(minutes=2) <= created - slot <= timedelta(minutes=30):
            return None, 'Scheduled event was admitted outside its bounded calendar window'
    elif event == 'workflow_dispatch':
        if not requested:
            return None, 'Production dispatch requires an explicit intended slot'
        slot = parse_slot(requested)
    else:
        return None, 'Unsupported production admission event'
    # Recovery is same UTC day, no bulk/backlog/future dispatch; reserve runtime before next slot.
    following = next((slot.replace(hour=h) for h in (14, 18, 22) if h > slot.hour),
                     (slot + timedelta(days=1)).replace(hour=0, minute=0))
    if slot.date() != now.date() or now < slot or now - slot > timedelta(hours=3) or now + timedelta(minutes=30) > following:
        return None, 'Slot is future, stale or too close to the next cadence boundary'
    return slot, None


def issues():
    result = []
    for page in range(1, 101):
        batch = clips.github('GET', 'issues', params={'state': 'all', 'per_page': 100, 'page': page})
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise ValueError('Slot ledger pagination incomplete; hold')


def record(issue):
    if issue.get('pull_request') or not issue['title'].startswith(PREFIX):
        raise ValueError('Not a slot record')
    data = json.loads(issue['body'])
    if data.get('version') != VERSION or issue['title'] != PREFIX + data.get('slot', ''):
        raise ValueError('Slot record identity mismatch')
    return data


def get_claim(proof):
    issue = clips.github('GET', 'issues/' + str(int(proof['issue'])))
    data = record(issue)
    if any(data.get(k) != proof.get(k) for k in ('slot', 'owner_run_id', 'owner_attempt', 'nonce', 'version')):
        raise ValueError('Slot proof does not match the durable owner')
    return issue, data


def patch_record(issue, data):
    clips.github('PATCH', 'issues/' + str(issue['number']), json={'body': json.dumps(data, indent=2)})


def trusted_live_run(run_id):
    if not str(run_id).isdigit():
        raise ValueError('Invalid admission run')
    run = clips.github('GET', 'actions/runs/' + str(run_id))
    if (run.get('head_repository', {}).get('full_name') != os.environ['GITHUB_REPOSITORY']
            or run.get('head_branch') != 'main' or run.get('path') != '.github/workflows/daily-video.yml'
            or run.get('event') not in ('schedule', 'workflow_dispatch')):
        raise ValueError('Untrusted production admission run')
    if str(run.get('id')) != str(run_id) or run.get('head_sha') != os.environ.get('GITHUB_SHA'):
        raise ValueError('Admission run/commit differs from the executing main workflow')
    return run


def admit(output):
    if os.environ.get('CLIP_PUBLISH_ENABLED') != 'true' or os.environ.get('CLIP_AUTO_PUBLISH_ENABLED') != 'true':
        return None, 'Existing publishing switches are disabled; no paid work admitted'
    run = trusted_live_run(os.environ['GITHUB_RUN_ID'])
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    slot, reason = resolve(run['event'], event.get('schedule'), os.environ.get('ARCHIVE_SLOT_REQUEST'),
                           clips.timestamp(run['created_at']), utc_now())
    if reason:
        return None, reason
    key = slot_name(slot)
    # Shared archive-previews serialization makes check/create mutually exclusive.
    if any(i['title'] == PREFIX + key for i in issues()):
        return None, 'Slot is durably occupied; retry/closure never releases it'
    data = {'version': VERSION, 'slot': key, 'owner_run_id': str(run['id']),
            'owner_attempt': str(os.environ.get('GITHUB_RUN_ATTEMPT', '1')), 'nonce': uuid.uuid4().hex,
            'phase': 'claimed', 'admission_event': run['event'], 'trigger_cron': event.get('schedule'),
            'observed_run_created_at': run['created_at'], 'head_sha': run['head_sha'],
            'claimed_at': utc_now().isoformat(), 'note': 'Occupied before generation. No publication implied. Closing never releases this slot.'}
    issue = clips.github('POST', 'issues', json={'title': PREFIX + key, 'body': json.dumps(data, indent=2)})
    proof = {k: data[k] for k in ('version', 'slot', 'owner_run_id', 'owner_attempt', 'nonce')}
    proof['issue'] = issue['number']
    root = Path(output); root.mkdir(parents=True, exist_ok=True)
    (root / 'slot-admission.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof, None


def require_generation(output):
    if os.environ.get('GITHUB_REF') != 'refs/heads/main' or os.environ.get('GITHUB_ACTIONS') != 'true':
        return None  # Local/branch private previews retain their existing non-public workflow gates.
    path = Path(output) / 'slot-admission.json'
    if not path.exists():
        raise ValueError('Production generation requires a durable current-run slot claim before paid work')
    proof = json.loads(path.read_text())
    _, data = get_claim(proof)
    if (data['phase'] != 'claimed' or proof['owner_run_id'] != os.environ['GITHUB_RUN_ID']
            or proof['owner_attempt'] != os.environ.get('GITHUB_RUN_ATTEMPT', '1')):
        raise ValueError('Generation requires the current attempt exclusive claimed slot')
    return proof


def mark_ready(output):
    root = Path(output); manifest = json.loads((root / 'manifest.json').read_text())
    proof = manifest['slot_admission']; issue, data = get_claim(proof)
    if (data['phase'] != 'claimed' or proof['owner_run_id'] != os.environ['GITHUB_RUN_ID']
            or proof['owner_attempt'] != os.environ.get('GITHUB_RUN_ATTEMPT', '1') or len(manifest['clips']) != 1):
        raise ValueError('Ready transition requires original slot owner and one checked clip')
    clip = manifest['clips'][0]
    if clips.file_hash(root / clips.identifier(clip['id']) / 'clip.mp4') != clip['sha256']:
        raise ValueError('Ready preview fingerprint mismatch')
    data.update(phase='preview_ready', manifest_digest=clips.digest(manifest),
                clip_id=clip['id'], video_sha256=clip['sha256'])
    patch_record(issue, data)


def publication_candidate(run_id):
    run = clips.verify_run(run_id)
    owners = [i for i in issues() if i['title'].startswith(PREFIX)
              and record(i).get('owner_run_id') == str(run_id)]
    return (len(owners) == 1 and record(owners[0]).get('phase') == 'preview_ready'
            and record(owners[0]).get('owner_attempt') == str(run.get('run_attempt', 1)))


def verify_publication(manifest, run_id, run=None):
    proof = manifest.get('slot_admission')
    if not proof or proof['owner_run_id'] != str(run_id):
        raise ValueError('Preview lacks exclusive calendar-slot provenance; no publication')
    issue, data = get_claim(proof)
    run = run or clips.verify_run(run_id)
    if proof['owner_attempt'] != str(run.get('run_attempt', 1)):
        raise ValueError('Preview belongs to a different run attempt; no publication')
    if data['phase'] != 'preview_ready' or data.get('manifest_digest') != clips.digest(manifest):
        raise ValueError('Slot preview is changed, consumed or ambiguous; no publication')
    return issue, data


def begin_publication(manifest, run_id):
    issue, data = verify_publication(manifest, run_id)
    data.update(phase='publishing', publishing_run_id=os.environ['GITHUB_RUN_ID'],
                publishing_attempt=os.environ.get('GITHUB_RUN_ATTEMPT', '1'))
    # Shared archive-publication serialization; crash/ambiguity retains the consumed phase.
    patch_record(issue, data)


def finish_publication(manifest):
    issue, data = get_claim(manifest['slot_admission'])
    if data['phase'] != 'publishing' or data.get('publishing_run_id') != os.environ['GITHUB_RUN_ID']:
        raise ValueError('Publication owner mismatch; reconcile without resubmitting')
    data.update(phase='submission_attempt_finished', note='Read individual platform delivery in the clip-publication ledger. Accepted is not published.')
    patch_record(issue, data)


def mark_failed(output):
    path = Path(output) / 'slot-admission.json'
    if not path.exists():
        return
    proof = json.loads(path.read_text()); issue, data = get_claim(proof)
    if data['phase'] == 'claimed' and proof['owner_run_id'] == os.environ['GITHUB_RUN_ID']:
        data['phase'] = 'preparation_failed'
        patch_record(issue, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['admit', 'ready', 'failed', 'publication-candidate'])
    parser.add_argument('--output', default='clip-output')
    parser.add_argument('--run-id')
    args = parser.parse_args()
    if args.command == 'admit':
        proof, reason = admit(args.output)
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as f:
            f.write('allowed=' + ('true' if proof else 'false') + '\n')
        print('Exclusive slot admitted before generation.' if proof else 'Archive slot held: ' + reason)
    elif args.command == 'ready':
        mark_ready(args.output)
    elif args.command == 'failed':
        mark_failed(args.output)
    else:
        allowed = publication_candidate(args.run_id)
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as f:
            f.write('allowed=' + str(allowed).lower() + '\n')
        print('Exclusive ready slot found.' if allowed else 'Publication held: no exclusive ready slot; no side effects.')


if __name__ == '__main__':
    main()
