"""Погодные поправки v2: эффект дождя зависит от часа (s15), проверяем на бэктесте.

Сравниваем профиль 2 недели без погоды, с прежней поправкой (s05) и с поправкой по часовым
полосам. Чтобы ошибка уровня не маскировала эффект погоды, считаем ещё и скор после
масштабирования прогноза под фактическую сумму маршрута за горизонт (оракул уровня).
Запуск: uv run python analysis/s16_weather_features.py
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from common import TABLES, wape_score
from models import ProfileConfig, profile_forecast
from s06_backtest import FOLDS, load_frame

PEAK_HOURS = set(range(6, 10)) | set(range(16, 20))


@dataclass(frozen=True)
class Weather:
    precip_day: float = 0.0  # log-эффект на 1 мм за день
    wet_offpeak: float = 0.0  # log-эффект часа с осадками ≥0.5 мм вне пиков
    wet_peak: float = 0.0  # то же в пиковые часы
    frost: float = 0.0  # log-эффект на 1 °C ниже -10


def apply_weather(pred: np.ndarray, grid: pd.DataFrame, w: Weather) -> np.ndarray:
    wet = (grid.precipitation.fillna(0) >= 0.5).to_numpy()
    peak = grid.hour.isin(PEAK_HOURS).to_numpy()
    adj = (w.precip_day * grid.precip_day.fillna(0).to_numpy()
           + np.where(wet & peak, w.wet_peak, 0.0) + np.where(wet & ~peak, w.wet_offpeak, 0.0)
           + w.frost * np.clip(-10 - grid.temp_day.fillna(0).to_numpy(), 0, None))
    return pred * np.exp(adj)


VARIANTS = {
    "без погоды": Weather(),
    "только осадки за день (-0.74 %/мм)": Weather(precip_day=-0.0074),
    "осадки за день + мороз": Weather(precip_day=-0.0074, frost=-0.0178),
    "дождь по часам: пик -1.5 %, межпик -6.5 %": Weather(wet_peak=-0.015, wet_offpeak=-0.067),
    "дождь по часам + мороз": Weather(wet_peak=-0.015, wet_offpeak=-0.067, frost=-0.0178),
    "день + дождь по часам + мороз": Weather(precip_day=-0.004, wet_peak=-0.015, wet_offpeak=-0.067, frost=-0.0178),
}


def oracle_route_level(y: pd.Series, p: np.ndarray, route: pd.Series) -> float:
    ps = pd.Series(p).groupby(route.to_numpy()).transform("sum").to_numpy()
    ys = y.groupby(route.to_numpy()).transform("sum").to_numpy()
    return wape_score(y, np.where(ps > 0, p * ys / np.where(ps > 0, ps, 1), 0))


def main() -> None:
    pd.set_option("display.width", 220)
    full = load_frame()
    rows = []
    for fold in FOLDS:
        origin, end = pd.Timestamp(fold.origin), pd.Timestamp(fold.end)
        hist = full[full.date <= origin]
        grid = full[(full.date > origin) & (full.date <= end)].reset_index(drop=True)
        base = profile_forecast(hist, grid.drop(columns="boardings"), origin, ProfileConfig(weeks=2))
        for name, w in VARIANTS.items():
            p = apply_weather(base, grid, w)
            rows.append({"fold": fold.name[:1], "model": name, "raw": wape_score(grid.boardings, p),
                         "oracle_level": oracle_route_level(grid.boardings, p, grid.route)})
    res = pd.DataFrame(rows)
    res.to_csv(TABLES / "exp2_weather_features.csv", index=False, float_format="%.4f")
    for col in ("raw", "oracle_level"):
        pv = res.pivot(index="model", columns="fold", values=col).loc[list(VARIANTS)]
        pv["среднее"] = pv.mean(axis=1)
        base_row = pv.loc["без погоды"]
        print(f"\n{col} (прирост к «без погоды», п.п.):")
        print(((pv - base_row) * 100).round(2).to_string())


if __name__ == "__main__":
    main()
