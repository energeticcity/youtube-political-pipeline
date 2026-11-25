"""Cheap scheduler gate: poll frequently, reserve at most one batch per local hour."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo

TZ=ZoneInfo('America/Dawson_Creek')
QUEUE='[gta6-cloud-queue] Active queue'
POST='[gta6-cloud-post] '
MIN_COMMENTARY_SECONDS=12


def window_for(current):
    local=current.astimezone(TZ)
    if not 7<=local.hour<=19:return None
    return local.date().isoformat()+('-pm' if local.hour>=15 else '-am')


def decision(issues,current):
    local=current.astimezone(TZ);slot=local.strftime('%Y-%m-%dT%H')
    window=window_for(current)
    if window is None:return {'required':False,'reason':'outside discovery/posting hours','slot':slot}
    queues=[json.loads(i.get('body') or '{}') for i in issues if i.get('title')==QUEUE]
    if len(queues)!=1:raise ValueError('Expected exactly one active queue')
    queue=queues[0]
    last=queue.get('last_discovery',{}).get('time')
    last_window=window_for(datetime.fromisoformat(last.replace('Z','+00:00'))) if last else None
    discovery_due=window not in queue.get('discovery_windows',{}) and last_window!=window
    rows=list(queue.get('history',[]))
    rows.extend(json.loads(i.get('body') or '{}') for i in issues if i.get('title','').startswith(POST))
    occupied=any(r.get('slot')==slot for r in rows)
    daily=sum(r.get('local_day')==local.date().isoformat() for r in rows)
    publication_due=8<=local.hour<=19 and not occupied and daily<12
    return {'required':discovery_due or publication_due,'discovery_due':discovery_due,
            'publication_due':publication_due,'slot':slot,'window':window,
            'reason':'work due' if discovery_due or publication_due else 'hour already reserved or daily cap reached'}


def main():
    if os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch' and os.environ.get('GTA6_REQUESTED_OPERATION')!='tick':
        result={'required':True,'reason':'explicit manual operation'}
    else:
        repo=os.environ['GITHUB_REPOSITORY']
        response=subprocess.run(['gh','api','--paginate','--slurp',f'repos/{repo}/issues?state=all&per_page=100'],
                                capture_output=True,text=True,timeout=90)
        if response.returncode:raise RuntimeError('Scheduler could not read the publication ledger')
        issues=[i for page in json.loads(response.stdout) for i in page if not i.get('pull_request')]
        result=decision(issues,datetime.now(timezone.utc))
    print(json.dumps(result))
    if os.environ.get('GITHUB_OUTPUT'):
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:
            output.write('required='+str(result['required']).lower()+'\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as summary:
            summary.write('GTA6 hourly check: '+result['reason']+'; '+result.get('slot','manual')+'\n')


if __name__=='__main__':main()
