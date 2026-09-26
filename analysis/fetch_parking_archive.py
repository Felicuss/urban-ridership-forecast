"""Fetch only public 2025 observations, pinned to the inspected revision.

Data: Danil Matrosov / ParkOut, derived from Moscow Department of Transport
public parking data; CC BY 4.0. Third-party source code is never executed.
"""
import concurrent.futures
import hashlib
import json
from pathlib import Path

import requests

REVISION = '5e7ca2096959f2557c0f05714bb534a2f5bdde6c'
SOURCE = 'https://github.com/matrosovcmtn/moscow-parking-occupancy'
OUT = Path(__file__).resolve().parents[1]/'data/research_094/parking'
FILES = ['README.md','DATA_LICENSE','data/parking_spots.parquet'] + [
    f'data/occupancy_2025-{m:02d}.parquet' for m in range(3,13)]


def fetch(name):
    url = f'https://raw.githubusercontent.com/matrosovcmtn/moscow-parking-occupancy/{REVISION}/{name}'
    response = requests.get(url,timeout=50)
    response.raise_for_status()
    assert len(response.content) < 2_000_000
    if name.endswith('.parquet'):
        assert response.content[:4] == response.content[-4:] == b'PAR1'
    path = OUT/Path(name).name
    path.write_bytes(response.content)
    return dict(file=path.name,url=url,bytes=len(response.content),
                sha256=hashlib.sha256(response.content).hexdigest())


if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        entries = list(pool.map(fetch,FILES))
    (OUT/'manifest.json').write_text(json.dumps(dict(source=SOURCE,revision=REVISION,
        files=entries),indent=2)+'\n')
    print('Downloaded',len(entries),'files;',sum(x['bytes'] for x in entries),'bytes')
