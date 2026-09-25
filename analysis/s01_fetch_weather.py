"""Почасовая погода Москвы за 2025 год из Open-Meteo Historical Weather API (реанализ ERA5).

API без ключа, лицензия данных CC BY 4.0: https://open-meteo.com/en/docs/historical-weather-api
Точка - центр Москвы, время в Europe/Moscow (UTC+3 без перехода на летнее время).
Запуск: uv run python analysis/s01_fetch_weather.py
"""

import pandas as pd
import requests

from common import ROOT

URL = "https://archive-api.open-meteo.com/v1/archive"
OUT = ROOT / "external" / "weather_moscow_2025_hourly.csv"
HOURLY = [
    "temperature_2m",
    "apparent_temperature",
    "precipitation",
    "rain",
    "snowfall",
    "snow_depth",
    "weather_code",
    "cloud_cover",
    "wind_speed_10m",
]
PARAMS = {
    "latitude": 55.7558,
    "longitude": 37.6173,
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "hourly": ",".join(HOURLY),
    "timezone": "Europe/Moscow",
}


def main() -> None:
    resp = requests.get(URL, params=PARAMS, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    df = pd.DataFrame(payload["hourly"])
    df = df.rename(columns={"time": "ts"})
    df["ts"] = pd.to_datetime(df["ts"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    missing = df[HOURLY].isna().sum()
    print(f"{len(df)} rows {df.ts.min()} .. {df.ts.max()} -> {OUT}")
    print("missing values:", missing[missing > 0].to_dict() or "none")


if __name__ == "__main__":
    main()
