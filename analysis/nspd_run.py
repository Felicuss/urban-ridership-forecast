"""One finite NSPD collection run: validate pilot, collect, export, then exit.

Does not restart failed collection or remove STOP. Intended to run under
caffeinate/nohup while the user works on other tasks.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

from nspd_export import export, completeness

ROOT=Path(__file__).resolve().parents[1]


def run(directory):
    directory=Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    lock=directory/'pipeline.lock'
    fd=os.open(lock, os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    requested=['view']

    def status(stage, **extra):
        payload=dict(stage=stage, pid=os.getpid(), updated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            groups=requested, **extra)
        tmp=directory/'run_status.json.tmp'
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n')
        tmp.replace(directory/'run_status.json')
        print(json.dumps(payload, ensure_ascii=False), flush=True)

    def config():
        p=directory/'run_config.json'
        groups=json.loads(p.read_text()).get('groups', ['view']) if p.exists() else ['view']
        if not groups or groups[0] != 'view' or any(g not in ['view','parcels','sparse'] for g in groups):
            raise ValueError('Run groups must start with view and use only known categories')
        return list(dict.fromkeys(groups))

    def collect(group, limit=None):
        cmd=[sys.executable, str(ROOT/'analysis/nspd_collect.py'), '--group', group,
             '--out', str(directory), '--tiles', str(directory/('tiles_4km.csv' if group=='sparse' else 'tiles_2km.csv'))]
        if limit:
            cmd+=['--limit', str(limit)]
        result=subprocess.run(cmd, cwd=ROOT)
        if result.returncode:
            raise RuntimeError(f'Collector stopped with exit code {result.returncode}; inspect STOP and log.txt')

    try:
        requested=config()
        if (directory/'STOP').exists():
            raise RuntimeError('Existing STOP: no requests made')
        q=export(directory, ['view'])
        already=q['coverage']['view']['completed_root_tiles']
        if already < 3:
            status('three_tile_check')
            collect('view', 3-already)
            q=export(directory, ['view'])
        if not q['building_pilot_pass']:
            raise RuntimeError('Three-tile building QA failed; inspect tables/quality.json')
        already=q['coverage']['view']['completed_root_tiles']
        if already < 50:
            status('pilot_50')
            collect('view', 50-already)
            q=export(directory, ['view'])
        if not q['building_pilot_pass'] or q['coverage']['view']['completed_root_tiles'] < 50:
            raise RuntimeError('50-tile pilot incomplete or QA failed; no full run started')
        completed=[]
        while True:
            requested=config()
            pending=[g for g in requested if g not in completed]
            if not pending:
                break
            group=pending[0]
            coverage,_=completeness(directory, [group])
            if not coverage[group]['complete']:
                status('collect_'+group)
                collect(group)
            completed.append(group)
            q=export(directory, completed)
            if not q['coverage'][group]['complete']:
                raise RuntimeError(f'{group}: incomplete tiles; no automatic restart')
        if not q['complete']:
            raise RuntimeError('Export QA found incomplete coverage or geometry errors')
        status('complete', quality='tables/quality.json')
    except Exception as exc:
        # Preserve whatever was collected even if the portal or quality gate stops.
        try:
            export(directory, requested)
        except Exception as export_error:
            print('Partial export error:', str(export_error), flush=True)
        reason=str(exc)
        if not (directory/'STOP').exists():
            (directory/'STOP').write_text(dt.datetime.now(dt.timezone.utc).isoformat()+' '+reason+'\n')
        status('stopped', reason=reason)
        return 3
    finally:
        lock.unlink(missing_ok=True)
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out', default=str(ROOT/'data/nspd_moscow'))
    args=parser.parse_args()
    sys.exit(run(args.out))
