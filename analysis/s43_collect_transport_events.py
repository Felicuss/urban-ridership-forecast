"""Cache public Deptrans posts; export only relevant tram posts for manual review.

Run with the research environment: python analysis/s43_collect_transport_events.py
The interval includes November–December 2025 and surrounding announcements.
Raw pages and review text stay in ignored data/. No effect size is invented here.
"""
from __future__ import annotations

import concurrent.futures
import json
import time
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/deptrans_archive"


def page(before):
    path = CACHE / f"before_{before}.html"
    if not path.exists():
        for attempt in range(3):
            try:
                request = urllib.request.Request(
                    f"https://t.me/s/DtOperativno?before={before}",
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                with urllib.request.urlopen(request, timeout=35) as response:
                    path.write_bytes(response.read())
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1 + attempt)
    return parse_page(path.read_text())


def parse_page(html):
    """Use the message body, never the quoted parent (which may describe a delay)."""
    soup = BeautifulSoup(html, "html.parser")
    result = []
    for node in soup.select('.tgme_widget_message[data-post]'):
        text, stamp = node.select_one('.js-message_text'), node.select_one('time[datetime]')
        reply = node.select_one('a.tgme_widget_message_reply')
        if text and stamp and stamp.get('datetime'):
            result.append(dict(post=node['data-post'], published=stamp['datetime'],
                               reply_to=reply.get('href') if reply else None,
                               text=text.get_text(' ', strip=True)))
    return result


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    posts = {}
    # Telegram returns 20 posts per page; 10-ID stride avoids gaps caused by album posts.
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for i, batch in enumerate(pool.map(page, range(22000, 24531, 10))):
            for post in batch:
                posts[post['post']] = post
            if i % 20 == 0:
                print(f"pages={i+1}, unique posts={len(posts)}", flush=True)
    (CACHE / 'all_posts.json').write_text(json.dumps(posts, ensure_ascii=False, indent=2))
    selected = [p for p in posts.values() if 'трамва' in p['text'].lower()]
    selected.sort(key=lambda p: p['published'])
    (CACHE / 'tram_posts.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2))
    (CACHE / 'tram_posts.txt').write_text('\n\n'.join(
        f"{p['published']} https://t.me/{p['post']}\n{p['text']}" for p in selected))
    print(f"Saved {len(selected)} tram posts from {len(posts)} total")


if __name__ == '__main__':
    main()
