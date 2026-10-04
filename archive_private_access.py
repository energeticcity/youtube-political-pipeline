"""Probe existing read access; private metric values never leave process memory."""
import json
import math
import os
from pathlib import Path
import requests
import clipping

POSTS=['sp_QnIMkjsq2Ki7OQrTKBrba','sp_PLtFooQYdwR0fuC0NYKRd','sp_EVH7urqItfhxWPWtR9q6','sp_iDHBcazPXx8aV8lf8Ro']
GROUPS={'views':{'views','view_count'},'engagement':{'likes','like_count','comments','comment_count','shares','share_count','saved'},
        'watch':{'averageViewDuration','averageViewPercentage','engagedViews','ig_reels_avg_watch_time','ig_reels_video_view_total_time','average_time_watched','total_time_watched'}}
BASE='https://api.postforme.dev/v1'

def available_groups(records,platform,account_id):
    available={name:False for name in GROUPS}
    for item in records if isinstance(records,list) else []:
        if not isinstance(item,dict) or item.get('social_account_id')!=account_id or item.get('social_post_id') not in POSTS or item.get('platform')!=platform:continue
        metrics=item.get('metrics')
        if not isinstance(metrics,dict):continue
        for name,fields in GROUPS.items():
            available[name] |= any(isinstance(metrics.get(k),(int,float)) and not isinstance(metrics.get(k),bool) and math.isfinite(metrics[k]) for k in fields)
    return available

def main():
    platform=os.environ['PLATFORM'];accounts=json.loads(os.environ['CLIP_DESTINATIONS_JSON'])
    account_id=accounts[platform];clipping.identifier(account_id);key=os.environ['POSTFORME_API_KEY']
    headers={'Authorization':'Bearer '+key}
    readable=False;available={name:False for name in GROUPS}
    # Catch without printing response, private values, account data, exception text or URLs.
    try:
        account=requests.get(BASE+'/social-accounts/'+account_id,headers=headers,timeout=45)
        if account.ok and account.json().get('platform')==platform and account.json().get('status')=='connected':
            response=requests.get(BASE+'/social-account-feeds/'+account_id,headers=headers,
                params={'social_post_id':POSTS,'expand':'metrics','limit':20},timeout=45)
            if response.ok:
                data=response.json();available=available_groups(data.get('data',[]) if isinstance(data,dict) else data,platform,account_id);readable=True
    except Exception:
        pass
    # Access booleans only, never any metric value or private record.
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as target:
        target.write('readable='+str(readable).lower()+'\n')
        for name,value in available.items():target.write(name+'='+str(value).lower()+'\n')
    print('Existing configured read access checked. Private values not exported.')

if __name__=='__main__':main()
