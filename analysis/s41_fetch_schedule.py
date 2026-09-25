"""Интервалы движения трамваев по часам из открытого расписания transport.mos.ru.

Справочник организаторов даёт расписание только одного рейса маршрута 1 (15 строк), поэтому
частоту движения берём с сайта Дептранса: https://transport.mos.ru/transport/schedule. На
странице поиска для каждого маршрута есть время работы и интервал по часам, отдельно для будней
и выходных и для каждого направления. Это действующее расписание на дату выгрузки, а не на
ноябрь-декабрь 2025: сервис показывает его как оценку числа рейсов в час.

Выход: external/transport_mos_schedule.csv, одна строка на маршрут × тип дня × направление ×
интервал часов. Запуск: uv run python analysis/s41_fetch_schedule.py
"""

import datetime as dt
import html
import re
import time

import pandas as pd
import requests

from common import ROOT, ROUTES

URL = "https://transport.mos.ru/transport/schedule"
# следующие страницы списка сайт подгружает этим ajax-запросом при прокрутке
PAGE_URL = "https://transport.mos.ru/ru/ajax/App/V2_ScheduleV2Controller/getRoutesList"
MAX_PAGES = 10
UA = {"User-Agent": "Mozilla/5.0 (hackathon research; tram load forecast)"}
OUT = ROOT / "external" / "transport_mos_schedule.csv"
DAY_TYPES = {"weekday": 1, "weekend": 0}  # значение mgt_schedule[workTime] на сайте
PAUSE_S = 1.0

ROW = re.compile(r'<a class="ts-row[^"]*" href="(/transport/schedule/route/\d+)">(.*?)</a>', re.S)
SPAN = re.compile(r"(\d{2}):(\d{2})\s*-\s*(\d{2}):(\d{2})</td>\s*<td>\s*(\d+)\s*мин", re.S)


def text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def fetch(route: int, work_time: int, direction: int) -> list[str]:
    """Все страницы поиска по номеру: у однозначных номеров трамвай бывает на 2-7 странице."""
    params = {"mgt_schedule[search]": str(route), "mgt_schedule[workTime]": str(work_time),
              "mgt_schedule[direction]": str(direction)}
    resp = requests.get(URL, params=params, headers=UA, timeout=60)
    resp.raise_for_status()
    pages = [resp.text]
    count = re.search(r'data-count-pages="(\d+)"', resp.text)
    for page in range(2, min(int(count.group(1)) if count else 1, MAX_PAGES) + 1):
        time.sleep(PAUSE_S)
        more = requests.get(PAGE_URL, params={**params, "page": str(page)},
                            headers={**UA, "X-Requested-With": "XMLHttpRequest"}, timeout=60)
        more.raise_for_status()
        pages.append(more.text)
    return pages


def parse_rows(page: str, route: int) -> list[dict]:
    """Строки трамвая с нужным номером: время работы и интервалы по часам."""
    rows = []
    for href, body in ROW.findall(page):
        number = re.search(r'<div class="ts-number">(.*?)</div>', body, re.S)
        if "icon-tramway" not in body or number is None or text(number.group(1)) != str(route):
            continue
        title = text(re.search(r'<div class="ts-title">(.*?)</div>', body, re.S).group(1))
        hours = re.search(r"с (\d{2}:\d{2}) по (\d{2}:\d{2})", text(body))
        for h1, m1, h2, m2, minutes in SPAN.findall(body):
            rows.append({"route": route, "title": title, "page": "https://transport.mos.ru" + href,
                         "service_from": hours.group(1) if hours else None,
                         "service_to": hours.group(2) if hours else None,
                         "span_from": f"{h1}:{m1}", "span_to": f"{h2}:{m2}", "headway_min": int(minutes)})
    return rows


def main() -> None:
    parts = []
    for route in ROUTES:
        for day_type, work_time in DAY_TYPES.items():
            for direction in (0, 1):
                rows = [r for page in fetch(route, work_time, direction) for r in parse_rows(page, route)]
                parts += [{**r, "day_type": day_type, "direction": direction} for r in rows]
                print(f"маршрут {route:>2} {day_type:7s} направление {direction}: интервалов {len(rows)}")
                time.sleep(PAUSE_S)
    df = pd.DataFrame(parts)
    df["fetched_at"] = dt.date.today().isoformat()
    cols = ["route", "day_type", "direction", "title", "service_from", "service_to", "span_from", "span_to",
            "headway_min", "page", "fetched_at"]
    df[cols].to_csv(OUT, index=False)
    print(f"{OUT.name}: {len(df)} строк, маршрутов {df.route.nunique()}")


if __name__ == "__main__":
    main()
