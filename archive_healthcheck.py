#!/usr/bin/env python3
"""Read-only GitHub snapshot; never generates, uploads, retries, or schedules posts."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime, timezone

REPO = 'energeticcity/youtube-political-pipeline'


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True)


def snapshot():
    runs = json.loads(gh('run', 'list', '--repo', REPO, '--limit', '100', '--json',
                         'databaseId,workflowName,status,conclusion,createdAt,event,headSha,url'))
    variables = json.loads(gh('variable', 'list', '--repo', REPO, '--json', 'name,value'))
    config = {v['name']: v['value'] for v in variables if v['name'] in {
        'CLIP_PUBLISH_ENABLED', 'CLIP_AUTO_PUBLISH_ENABLED', 'CLIP_DESTINATIONS_JSON',
        'CLIP_PAUSED_DESTINATIONS_JSON'}}
    pages = json.loads(gh('api', '--paginate', '--slurp', f'repos/{REPO}/issues?state=all&per_page=100'))
    publications = []
    for issue in (i for page in pages for i in page):
        if issue['title'].startswith('[clip-publication] '):
            match = re.search(r'Post for Me ID: `([A-Za-z0-9_-]+)`', issue.get('body') or '')
            publications.append({'issue': issue['number'], 'episode': issue['title'],
                                 'post_id': match[1] if match else None, 'url': issue['html_url']})
    deliveries, errors = {}, []
    checks = [r for r in runs if r['workflowName'] == 'Check Archive Delivery'
              and r['status'] == 'completed' and r['conclusion'] == 'success'][:5]
    for run in checks:
        try:
            log = gh('run', 'view', str(run['databaseId']), '--repo', REPO, '--log')
            match = re.search(r'POST_ID: ([A-Za-z0-9_-]+)', log)
            if not match or match[1] in deliveries:
                continue
            with tempfile.TemporaryDirectory(prefix='archive-health-') as tmp:
                gh('run', 'download', str(run['databaseId']), '--repo', REPO,
                   '--name', 'archive-delivery', '--dir', tmp)
                result = json.loads((Path(tmp) / 'delivery.json').read_text())
            deliveries[match[1]] = {'checked_at': run['createdAt'], 'run_url': run['url'], 'platforms': result}
        except (subprocess.CalledProcessError, OSError, ValueError):
            errors.append({'run_id': run['databaseId'], 'error': 'delivery evidence unavailable'})
    for publication in publications:
        evidence = deliveries.get(publication['post_id'])
        publication['delivery'] = evidence or {'status': 'unverified; provider acceptance is not delivery'}
    return {'checked_at': datetime.now(timezone.utc).isoformat(), 'repository': REPO,
            'config': config, 'recent_runs': runs, 'publications': publications, 'read_errors': errors,
            'next_check': 'For unverified posts, dispatch archive-delivery.yml with post_id, then rerun this snapshot. '
                          'Review every platform and its individual video URL; never retry an entire partial batch.'}


if __name__ == '__main__':
    print(json.dumps(snapshot(), indent=2))
