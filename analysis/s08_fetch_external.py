"""Выгрузка внешних источников в external/. Каждый источник - открытый, без ключа.

1. data.mos.ru, набор 62521 «Месячный пассажиропоток по всем видам общественного транспорта»
   https://data.mos.ru/opendata/7704786030-mesyachniy-passajiropotok-po-vsem-vidam-obshchestvennogo-transporta-v-gorode-moskve
2. isdayoff.ru - производственный календарь РФ 2025 с предпраздничными днями
   https://isdayoff.ru/api/getdata?year=2025&cc=ru&pre=1
3. Open-Meteo - восход, закат, световой день по Москве
   https://open-meteo.com/en/docs/historical-weather-api
4. OpenStreetMap (Overpass API) - геометрия трамвайных маршрутов и остановок, лицензия ODbL
   https://wiki.openstreetmap.org/wiki/Overpass_API
Запуск: uv run python analysis/s08_fetch_external.py
"""

import calendar
import datetime as dt
import json

import pandas as pd
import requests

from common import ROOT, ROUTES

EXT = ROOT / "external"
MONTHS_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь",
             "Ноябрь", "Декабрь"]
UA = {"User-Agent": "tram-forecast-hackathon/0.1 (research)"}


def fetch_datamos() -> pd.DataFrame:
    """Помесячный пассажиропоток. Эндпоинт портала отдаёт набор без API-ключа."""
    body = {"id": 114682, "epoch": "2026-09-15 15:00:47", "timestamp": 1, "criteria": ""}
    resp = requests.post("https://data.mos.ru/api/v2/odata/catalog/get", json=body, headers=UA, timeout=60)
    resp.raise_for_status()
    df = pd.DataFrame(resp.json()["response"])
    df["month"] = df["Month"].map({m: i + 1 for i, m in enumerate(MONTHS_RU)})
    df["days"] = [calendar.monthrange(y, m)[1] for y, m in zip(df["Year"], df["month"], strict=True)]
    df["per_day"] = df["PassengerTraffic"] / df["days"]
    out = df[["Year", "month", "TransportType", "PassengerTraffic", "days", "per_day"]]
    out = out.rename(columns={"Year": "year", "TransportType": "transport", "PassengerTraffic": "passengers"})
    out.to_csv(EXT / "datamos_62521_monthly_ridership.csv", index=False, float_format="%.1f")
    return out


def fetch_isdayoff(year: int = 2025) -> pd.DataFrame:
    """0 - рабочий, 1 - выходной, 2 - сокращённый рабочий (с pre=1), 8 - праздник (с holiday=1)."""
    resp = requests.get(f"https://isdayoff.ru/api/getdata?year={year}&cc=ru&pre=1&holiday=1", headers=UA, timeout=60)
    resp.raise_for_status()
    codes = resp.text.strip()
    start = dt.date(year, 1, 1)
    rows = [{"date": start + dt.timedelta(days=i), "isdayoff_code": int(c)} for i, c in enumerate(codes)]
    df = pd.DataFrame(rows)
    df.to_csv(EXT / f"production_calendar_{year}_isdayoff.csv", index=False)
    return df


def fetch_daylight() -> pd.DataFrame:
    params = {
        "latitude": 55.7558, "longitude": 37.6173, "start_date": "2025-01-01", "end_date": "2025-12-31",
        "daily": "sunrise,sunset,daylight_duration", "timezone": "Europe/Moscow",
    }
    resp = requests.get("https://archive-api.open-meteo.com/v1/archive", params=params, headers=UA, timeout=60)
    resp.raise_for_status()
    df = pd.DataFrame(resp.json()["daily"]).rename(columns={"time": "date"})
    df["daylight_hours"] = df["daylight_duration"] / 3600
    df.drop(columns="daylight_duration").to_csv(EXT / "daylight_moscow_2025.csv", index=False, float_format="%.3f")
    return df


def fetch_osm_routes() -> dict:
    """Отношения route=tram с нужными номерами в пределах Москвы: линии путей и остановки."""
    refs = "|".join(str(r) for r in ROUTES)
    query = f"""
    [out:json][timeout:180];
    relation["type"="route"]["route"="tram"]["ref"~"^({refs})$"](55.55,37.35,55.95,37.90);
    out geom;
    """
    headers = {**UA, "Accept": "application/json"}  # без Accept Overpass отвечает 406 или пустым ответом
    resp = requests.post("https://overpass-api.de/api/interpreter", data={"data": query}, headers=headers, timeout=240)
    resp.raise_for_status()
    data = resp.json()
    features = []
    for rel in data.get("elements", []):
        tags = rel.get("tags", {})
        for m in rel.get("members", []):
            if m["type"] == "way" and m.get("role", "") in ("", "forward", "backward") and "geometry" in m:
                coords = [[p["lon"], p["lat"]] for p in m["geometry"]]
                features.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords},
                                 "properties": {"route": tags.get("ref"), "kind": "track", "rel": rel["id"],
                                                "name": tags.get("name")}})
            elif m["type"] == "node" and m.get("role", "").startswith(("stop", "platform")) and "lat" in m:
                features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [m["lon"], m["lat"]]},
                                 "properties": {"route": tags.get("ref"), "kind": "stop", "rel": rel["id"],
                                                "role": m.get("role")}})
    geo = {"type": "FeatureCollection", "features": features,
           "attribution": "© OpenStreetMap contributors, ODbL 1.0"}
    (EXT / "osm_tram_routes.geojson").write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
    return geo


def main() -> None:
    EXT.mkdir(exist_ok=True)
    calendars = [(f"isdayoff {y}", lambda y=y: fetch_isdayoff(y)) for y in (2019, 2022, 2023, 2024, 2025)]
    for name, fn in (("data.mos.ru 62521", fetch_datamos), *calendars,
                     ("Open-Meteo daylight", fetch_daylight), ("OSM Overpass", fetch_osm_routes)):
        try:
            res = fn()
            size = len(res["features"]) if isinstance(res, dict) else len(res)
            print(f"{name}: ok, {size} rows/features")
        except requests.RequestException as exc:
            print(f"{name}: FAILED {exc}")


if __name__ == "__main__":
    main()
