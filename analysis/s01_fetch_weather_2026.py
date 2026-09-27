"""Погода Москвы по дням на 2026 год для оценки января-октября 2026 (artifacts/outlook.csv).

Два запроса к Open-Meteo без ключа (лицензия CC BY 4.0), точка - центр Москвы, время Europe/Moscow:
- архив (https://archive-api.open-meteo.com/v1/archive) с 01.01.2026 по последний день, где он заполнен;
- прогноз (https://api.open-meteo.com/v1/forecast, past_days=92, forecast_days=16) на дни после архива.
Дальше горизонта прогноза погоды нет, и оценка такие дни не поправляет.

Берём почасовые ряды и сворачиваем их в сутки двумя способами: за все 24 часа (precipitation_sum,
snowfall_sum, temperature_2m_mean - как в дневных рядах Open-Meteo) и за 6-22 ч (precip_6_22, temp_6_22) -
так считает признаки погоды модель (models.add_weather), и к ним относятся её коэффициенты.
Запуск: uv run python analysis/s01_fetch_weather_2026.py
"""

import datetime as dt

import pandas as pd
import requests

from common import ROOT

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OUT = ROOT / "external" / "weather_moscow_2026_daily.csv"
START, END = "2026-01-01", "2026-10-31"
HOURLY = ["precipitation", "snowfall", "temperature_2m"]
POINT = {"latitude": 55.7558, "longitude": 37.6173, "timezone": "Europe/Moscow"}
PAST_DAYS = 92
FORECAST_DAYS = 16
DAY_FROM, DAY_TO = 6, 22  # часы, по которым модель считает осадки и температуру дня
TIMEOUT_S = 60
MOSCOW = dt.timezone(dt.timedelta(hours=3))


def _hourly(url: str, params: dict) -> pd.DataFrame:
    resp = requests.get(url, params={**POINT, "hourly": ",".join(HOURLY), **params}, timeout=TIMEOUT_S)
    resp.raise_for_status()
    frame = pd.DataFrame(resp.json()["hourly"]).rename(columns={"time": "ts"})
    frame["ts"] = pd.to_datetime(frame.ts)
    return frame


def _daily(hourly: pd.DataFrame, source: str) -> pd.DataFrame:
    """Сутки, где заполнены все 24 часа: неполный последний день архива не берём."""
    h = hourly.dropna(subset=HOURLY).assign(date=lambda f: f.ts.dt.strftime("%Y-%m-%d"), hour=lambda f: f.ts.dt.hour)
    full = h.groupby("date").hour.transform("size") == 24
    h = h[full]
    day = h[h.hour.between(DAY_FROM, DAY_TO)].groupby("date").agg(precip_6_22=("precipitation", "sum"),
                                                                    temp_6_22=("temperature_2m", "mean"))
    whole = h.groupby("date").agg(precipitation_sum=("precipitation", "sum"), snowfall_sum=("snowfall", "sum"),
                                  temperature_2m_mean=("temperature_2m", "mean"))
    return whole.join(day).round(2).reset_index().assign(source=source)


def fetch(today: dt.date | None = None) -> pd.DataFrame:
    today = today or dt.datetime.now(MOSCOW).date()
    last = min(today - dt.timedelta(days=1), dt.date.fromisoformat(END))
    archive = _daily(_hourly(ARCHIVE_URL, {"start_date": START, "end_date": last.isoformat()}), "archive")
    forecast = _daily(_hourly(FORECAST_URL, {"past_days": PAST_DAYS, "forecast_days": FORECAST_DAYS}), "forecast")
    forecast = forecast[(forecast.date > archive.date.max()) & (forecast.date <= END)]
    out = pd.concat([archive, forecast], ignore_index=True).sort_values("date")
    gaps = pd.date_range(START, out.date.max()).strftime("%Y-%m-%d").difference(out.date)
    if len(gaps):
        raise ValueError(f"в погоде 2026 нет дней: {', '.join(gaps[:5])}")
    return out[["date", "precipitation_sum", "snowfall_sum", "temperature_2m_mean", "precip_6_22", "temp_6_22",
                "source"]]


def main() -> None:
    out = fetch()
    out.to_csv(OUT, index=False, lineterminator="\n")
    by_source = out.groupby("source").date.agg(["min", "max", "size"])
    print(f"{len(out)} дней -> {OUT}\n{by_source}")


if __name__ == "__main__":
    main()
