"""Read public Deptrans statistics posts; no accounts/private APIs are accessed.

Caches original pages and extracts dates/text/links for manual source verification.
Future external facts are explicitly permitted by the organizers (team QA).
This script does not assume that published passenger totals equal paid boardings.
"""
from __future__ import annotations

import concurrent.futures
import argparse
import json
import time
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'data/future_facts/dtroad'


def archive_page(before):
    # Telegram search pagination can stop after a handful of matches. Read the
    # unfiltered public archive, with overlap because albums consume several IDs.
    path=CACHE/f'before_{before}.html'
    if not path.exists():
        url=f'https://t.me/s/DtRoad?before={before}'
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url,timeout=25) as r:
                    path.write_bytes(r.read())
                break
            except Exception:
                if attempt==2:
                    raise
                time.sleep(attempt+1)
    soup=BeautifulSoup(path.read_text(),'html.parser')
    posts={}
    for node in soup.select('.tgme_widget_message[data-post]'):
        body=node.select_one('.js-message_text')
        stamp=node.select_one('time[datetime]')
        if body and stamp:
            posts[node['data-post']]=dict(source_url='https://t.me/'+node['data-post'],
                published=stamp['datetime'],text=body.get_text(' ',strip=True),
                links=[a.get('href') for a in body.select('a[href]')])
    return posts


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--before-start',type=int,default=53500)
    parser.add_argument('--before-end',type=int,default=59000)
    args=parser.parse_args()
    CACHE.mkdir(parents=True,exist_ok=True)
    posts={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for i,batch in enumerate(pool.map(archive_page,range(args.before_start,args.before_end+1,18))):
            posts.update(batch)
            if i%20==0:
                print('archive pages',i+1,'posts',len(posts),flush=True)
    items=sorted(posts.values(),key=lambda x:x['published'])
    (CACHE/'posts.json').write_text(json.dumps(items,ensure_ascii=False,indent=2)+'\n')
    chosen=[p for p in items if 'трамва' in p['text'].lower() and any(w in p['text'].lower() for w in ['поезд','пассажир','перевез'])]
    (CACHE/'statistics_posts.txt').write_text('\n\n'.join(
        p['published']+' '+p['source_url']+'\n'+p['text'] for p in chosen))
    print('DONE',len(items),'unique posts;',len(chosen),'with passenger/trip context',flush=True)


if __name__=='__main__':
    main()
