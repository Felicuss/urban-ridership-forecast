"""Погода на горизонте «сутки»: фактическая против прогноза, выпущенного накануне.

В сервисе прогноз на завтра строится до того, как погода случилась, поэтому поправку надо
считать по прогнозу погоды. Open-Meteo Previous Runs API хранит прогнозы прошлых запусков:
переменная *_previous_day1 - значение, которое модель давала для этого часа за 24 часа до него.

Бэктест: каждый день февраля-октября 2025 прогнозируем профилем за 2 недели от вечера
накануне. Погодная поправка нормирована на погоду окна профиля, коэффициент осадков оценён
только по данным до начала месяца (схема s31). Сравниваем без погоды, с фактической погодой
архива и с прогнозом накануне.
Запуск: uv run python analysis/s37_weather_forecast_day_ahead.py
"""

import numpy as np
import pandas as pd
import requests

from common import ROOT, TABLES, wape_score
from models import ProfileConfig, profile_forecast
from s06_backtest import load_frame
from s31_weather_probe import PRECIP_DAY, PRECIP_HOUR, causal_precip_coef, weather_log, window_norm

FORECAST = ROOT / "external" / "weather_moscow_2025_forecast_day1.csv"
PROFILE = ProfileConfig(weeks=2)
FIRST, LAST = "2025-02-01", "2025-10-31"


def fetch_forecast() -> pd.DataFrame:
    if FORECAST.exists():
        return pd.read_csv(FORECAST, parse_dates=["ts"])
    params = {"latitude": 55.7558, "longitude": 37.6173, "start_date": "2025-01-01", "end_date": "2025-12-31",
              "hourly": "precipitation_previous_day1,snowfall_previous_day1,temperature_2m_previous_day1",
              "timezone": "Europe/Moscow"}
    resp = requests.get("https://previous-runs-api.open-meteo.com/v1/forecast", params=params, timeout=120,
                        headers={"User-Agent": "tram-forecast/0.1 (research)"})
    resp.raise_for_status()
    df = pd.DataFrame(resp.json()["hourly"]).rename(columns={"time": "ts"})
    df["ts"] = pd.to_datetime(df.ts)
    df.to_csv(FORECAST, index=False)
    return df


def forecast_weather(grid: pd.DataFrame, fc: pd.DataFrame) -> pd.DataFrame:
    """Те же колонки, что даёт add_weather, но из прогноза накануне."""
    f = fc.assign(date=fc.ts.dt.normalize(), hour=fc.ts.dt.hour)
    day = (f[f.hour.between(6, 22)].groupby("date")
           .agg(precip_day=("precipitation_previous_day1", "sum"), temp_day=("temperature_2m_previous_day1", "mean")))
    hourly = f.set_index(["date", "hour"]).precipitation_previous_day1.rename("precipitation")
    out = grid.drop(columns=["precip_day", "temp_day", "precipitation"])
    out = out.join(day, on="date").join(hourly, on=["date", "hour"])
    return out


def main() -> None:
    pd.set_option("display.width", 200)
    full = load_frame()
    fc = fetch_forecast()
    rows, coefs = [], {}
    for day in pd.date_range(FIRST, LAST):
        month = day.to_period("M")
        if month not in coefs:  # коэффициент пересчитываем раз в месяц, только по прошлым данным
            coefs[month] = causal_precip_coef(full[full.date < month.start_time])
        k = coefs[month]
        ph = PRECIP_HOUR * k / PRECIP_DAY  # часовой коэффициент в той же пропорции, как в s31
        origin = day - pd.Timedelta(days=1)
        history = full[full.date <= origin]
        grid = full[full.date == day].reset_index(drop=True)
        base = profile_forecast(history, grid.drop(columns="boardings"), origin, PROFILE)
        norm = window_norm(history, origin, k, ph)
        n = norm.reindex(pd.MultiIndex.from_arrays([grid.kind, grid.hour])).fillna(1.0).to_numpy()
        grid_fc = forecast_weather(grid, fc)
        rows.append(pd.DataFrame({
            "date": day, "route": grid.route, "hour": grid.hour, "kind": grid.kind, "y": grid.boardings,
            "profile": base, "fact_weather": base * np.exp(weather_log(grid, k, ph)) / n,
            "forecast_weather": base * np.exp(weather_log(grid_fc, k, ph)) / n,
            "precip_fact": grid.precip_day, "precip_fc": grid_fc.precip_day, "coef": k}))
    res = pd.concat(rows, ignore_index=True)

    variants = ["profile", "fact_weather", "forecast_weather"]
    wet = res.precip_fact >= 1  # дни, где поправке есть что делать
    groups = {"все дни": res.y >= 0, "дни с осадками от 1 мм": wet, "сухие дни": ~wet}
    for m in range(2, 11):
        groups[f"месяц {m:02d}"] = res.date.dt.month == m
    table = pd.DataFrame([{"period": g, "days": res.date[sel].nunique(),
                           **{v: wape_score(res.y[sel], res[v][sel]) for v in variants}}
                          for g, sel in groups.items()])
    table["gain_fact_pp"] = (table.fact_weather - table.profile) * 100
    table["gain_forecast_pp"] = (table.forecast_weather - table.profile) * 100
    table.to_csv(TABLES / "exp_weather_day_ahead.csv", index=False, float_format="%.5f")
    print(table.round(4).to_string(index=False))

    daily = res.drop_duplicates("date")
    corr = daily.precip_fact.corr(daily.precip_fc)
    hit = ((daily.precip_fact >= 1) == (daily.precip_fc >= 1)).mean()
    print(f"\nосадки 06-22 ч, прогноз накануне против факта: корреляция {corr:.2f}, "
          f"совпадение «есть ≥1 мм или нет» {hit:.0%} дней; коэффициенты по месяцам: "
          f"{ {str(m): round(v, 4) for m, v in coefs.items()} }")


if __name__ == "__main__":
    main()
