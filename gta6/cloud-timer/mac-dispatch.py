"""Temporary Mac clock: dispatch existing cloud work without a running chat."""
from datetime import datetime,timezone
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import sys
from zoneinfo import ZoneInfo

REPO='energeticcity/youtube-political-pipeline'
GH='/opt/homebrew/bin/gh'
ROOT=Path.home()/'.local/share/gta6-cloud-clock'

def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    logger=logging.getLogger('gta6-clock');logger.setLevel(logging.INFO)
    handler=RotatingFileHandler(ROOT/'dispatch.log',maxBytes=1_000_000,backupCount=3)
    logger.addHandler(handler)
    current=datetime.now(timezone.utc)
    stamp=current.isoformat()
    local=current.astimezone(ZoneInfo('America/Dawson_Creek'))
    if not 7<=local.hour<=19:
        return
    identity=subprocess.run([GH,'api','user','--jq','.login'],capture_output=True,text=True,timeout=30)
    if identity.returncode or identity.stdout.strip()!='energeticcity':
        logger.error('%s STOP GitHub identity check failed',stamp);raise SystemExit(1)
    if '--check-only' in sys.argv:
        print('Verified GitHub account; clock targets the existing GTA6 workflow.');return
    result=subprocess.run([GH,'workflow','run','gta6-hourly.yml','--repo',REPO,'--ref','main','-f','operation=tick','-f','timer_source=mac-backup'],capture_output=True,text=True,timeout=60)
    if result.returncode:
        logger.error('%s FAIL GitHub dispatch exit=%s; credentials and response withheld',stamp,result.returncode)
        raise SystemExit(1)
    logger.info('%s DISPATCHED tick; local slot=%s',stamp,local.strftime('%Y-%m-%dT%H'))

if __name__=='__main__':main()
