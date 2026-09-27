"""Загруженность дорог Москвы за 2025 год из двух открытых источников.

1. data.mos.ru, набор 62525 «Карта среднемесячной загруженности дорог с индексами загруженности»
   (Дептранс): балл и процент загруженности по месяцам с июня 2020 года. Отдаётся тем же
   эндпоинтом без ключа, что и пассажиропоток 62521 в s08.
   https://data.mos.ru/opendata/62525
2. Баллы пробок и средняя скорость потока по данным ЦОДД из постов канала «Дептранс. Оперативно»:
   утром «На дорогах - 5 баллов по данным ЦОДД», вечером «Средняя скорость потока - 28 км/ч,
   движение оценивается в 7 баллов». Веб-превью канала открыто без авторизации и листается назад
   параметром before. ЦОДД пишет не каждый день, чаще в будни и при тяжёлой обстановке.
   https://t.me/s/DtOperativno

Сырые посты кэшируются в data/ (в git не идут), в external/ пишутся только посты с баллом
или скоростью: время, балл, скорость, ссылка на пост.
Запуск: uv run python analysis/s33_fetch_traffic.py
"""

import html
import re
import time

import pandas as pd
import requests

from common import DATA, ROOT

EXT = ROOT / "external"
CHANNEL = "DtOperativno"
FIRST_DAY, LAST_DAY = "2024-12-01", "2025-12-31"  # декабрь 2024 нужен для базы начала января
RAW = DATA / "telegram_dtoperativno.parquet"
UA = {"User-Agent": "Mozilla/5.0 (tram-forecast research)"}

SCORE = re.compile(r"(\d{1,2})\s*балл")
SPEED = re.compile(r"скорост[^.\d]{0,40}?(\d{2})\s*км/ч", re.I)
# Прогноз и сравнения с прошлым - не наблюдение текущей загруженности. Проверяем только
# предложение с баллом: «по прогнозам синоптиков» в погодной части поста балл не отменяет.
NOT_NOW = re.compile(r"ожида|прогноз|могут|может|достигнут|до \d{1,2} балл|прошл|вчера|рекорд|впервые", re.I)
SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


def fetch_datamos_congestion() -> pd.DataFrame:
    body = {"id": 114684, "epoch": "2026-09-01 15:00:21", "timestamp": 1, "criteria": ""}
    resp = requests.post("https://data.mos.ru/api/v2/odata/catalog/get", json=body, headers=UA, timeout=60)
    resp.raise_for_status()
    df = pd.DataFrame(resp.json()["response"])
    period = df.Period.str.split(".", expand=True).astype(int)
    out = pd.DataFrame({"year": period[1], "month": period[0], "congestion_score": df.CapacityRating,
                        "congestion_pct": df.CapacityPercentage}).sort_values(["year", "month"])
    out.to_csv(EXT / "datamos_62525_monthly_congestion.csv", index=False)
    return out


def fetch_page(before: int | None) -> list[dict]:
    url = f"https://t.me/s/{CHANNEL}" + (f"?before={before}" if before else "")
    for attempt in range(5):
        resp = requests.get(url, headers=UA, timeout=60)
        if resp.status_code == 200:
            break
        time.sleep(5 * (attempt + 1))
    resp.raise_for_status()
    posts = []
    for block in resp.text.split('<div class="tgme_widget_message_wrap')[1:]:
        post = re.search(r'data-post="[^/]+/(\d+)"', block)
        ts = re.search(r'<time datetime="([^"]+)"', block)
        body = re.search(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', block, re.S)
        if not (post and ts):
            continue
        text = re.sub(r"<br\s*/?>", "\n", body.group(1)) if body else ""
        posts.append({"id": int(post.group(1)), "ts_utc": ts.group(1),
                      "text": html.unescape(re.sub(r"<[^>]+>", "", text))})
    return posts


def fetch_channel() -> pd.DataFrame:
    if RAW.exists():
        return pd.read_parquet(RAW)
    rows, before = [], None
    while True:
        page = fetch_page(before)
        if not page:
            break
        rows += page
        oldest = min(p["id"] for p in page)
        if page[0]["ts_utc"] < FIRST_DAY or oldest <= 1:
            break
        before = oldest
        time.sleep(0.7)
    df = pd.DataFrame(rows).drop_duplicates("id").sort_values("id")
    df["ts"] = pd.to_datetime(df.ts_utc).dt.tz_convert("Europe/Moscow").dt.tz_localize(None)
    df = df.drop(columns="ts_utc").reset_index(drop=True)
    df.to_parquet(RAW, index=False)
    return df


def observed(text: str) -> tuple[float | None, float | None]:
    """Балл и скорость, которые пост сообщает как текущие; перечень улиц после «Интенсивное движение» не смотрим."""
    score = speed = None
    for s in SENTENCE.split(text.split("Интенсивное движение")[0]):
        if NOT_NOW.search(s):
            continue
        if score is None and (m := SCORE.search(s)) and int(m.group(1)) <= 10:
            score = float(m.group(1))
        if speed is None and (m := SPEED.search(s)):
            speed = float(m.group(1))
    return score, speed


def parse_posts(posts: pd.DataFrame) -> pd.DataFrame:
    p = posts[(posts.ts >= FIRST_DAY) & (posts.ts < pd.Timestamp(LAST_DAY) + pd.Timedelta(days=1))].copy()
    p[["score", "speed_kmh"]] = pd.DataFrame([observed(t) for t in p.text], index=p.index, dtype=float)
    p = p.dropna(subset=["score", "speed_kmh"], how="all")
    p["link"] = "https://t.me/" + CHANNEL + "/" + p.id.astype(str)
    out = p[["id", "ts", "score", "speed_kmh", "link"]]
    out.to_csv(EXT / "traffic_codd_posts_2025.csv", index=False)
    return out


def main() -> None:
    cong = fetch_datamos_congestion()
    print(f"data.mos.ru 62525: {len(cong)} месяцев, {cong.year.min()}-{cong.year.max()}")
    print(cong[cong.year == 2025].to_string(index=False))
    posts = fetch_channel()
    print(f"\nпостов канала: {len(posts)}, {posts.ts.min()} - {posts.ts.max()}")
    out = parse_posts(posts)
    days = out.dropna(subset=["score"]).ts.dt.date.nunique()
    print(f"с баллом или скоростью: {len(out)}, дней с баллом: {days}")


if __name__ == "__main__":
    main()
