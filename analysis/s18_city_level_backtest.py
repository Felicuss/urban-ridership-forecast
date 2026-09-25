"""Проверка внешнего уровня на бэктесте: профиль × сезонный множитель из data.mos.ru.

Для каждого фолда множитель месяца m = 1 + наклон × (город[m] / город[месяц отсечки] - 1), где
город - помесячный индекс трамвая Москвы на эквивалент рабочего дня (s09). Это та же схема,
что даёт уровень ноября-декабря в s10, только на прошлых месяцах 2025 года. Наклон 0.83
оценён по всем месяцам, поэтому проверяем и наклон 1.0 (без подгонки).
Запуск: uv run python analysis/s18_city_level_backtest.py (после s09 и s17)
"""

import numpy as np
import pandas as pd

from common import DATA, TABLES, wape_score
from models import ProfileConfig, profile_forecast
from s06_backtest import FOLDS, load_frame
from s09_external_factors import day_weights, routes_vs_city

DAILY_FM = ["Chronos-2 дневной", "t0-beta дневной"]


def city_multiplier(grid: pd.DataFrame, origin: pd.Timestamp, city: pd.Series, slope: float) -> np.ndarray:
    base = city[origin.month]
    ratio = grid.date.dt.month.map(lambda m: city[m] / base).to_numpy()
    return 1 + slope * (ratio - 1)


def main() -> None:
    pd.set_option("display.width", 220)
    idx, fitted_slope, _ = routes_vs_city(day_weights())
    city = idx["city"]
    full = load_frame()
    daily_fm = pd.read_parquet(DATA / "fm_daily_backtest_preds.parquet")
    rows = []
    for fold in FOLDS:
        origin, end = pd.Timestamp(fold.origin), pd.Timestamp(fold.end)
        grid = full[(full.date > origin) & (full.date <= end)].reset_index(drop=True)
        y = grid.boardings
        hist = full[full.date <= origin]
        prof = profile_forecast(hist, grid.drop(columns="boardings"), origin, ProfileConfig(weeks=2))
        fm = daily_fm[daily_fm.fold == fold.name].set_index(["route", "ts"])
        fm = fm.reindex(pd.MultiIndex.from_arrays([grid.route, grid.ts]))
        fm_mean = fm[DAILY_FM].mean(axis=1).fillna(0).to_numpy()
        variants = {"профиль 2 нед": prof, "дневные Chronos-2 + t0": fm_mean}
        for slope, tag in ((fitted_slope, f"наклон {fitted_slope:.2f}"), (1.0, "наклон 1.0")):
            k = city_multiplier(grid, origin, city, slope)
            variants[f"профиль × городской уровень ({tag})"] = prof * k
            variants[f"смесь: профиль × городской уровень ({tag}) и дневные FM"] = (prof * k + fm_mean) / 2
        for name, p in variants.items():
            rows.append({"fold": fold.name[:1], "model": name, "wape_score": wape_score(y, p),
                         "bias_pct": (p.sum() / y.sum() - 1) * 100})
        mults = {m: round(1 + fitted_slope * (city[m] / city[origin.month] - 1), 3)
                 for m in sorted(grid.date.dt.month.unique())}
        print(f"{fold.name}: множители по месяцам {mults}")
    res = pd.DataFrame(rows)
    res.to_csv(TABLES / "exp2_city_level.csv", index=False, float_format="%.4f")
    pv = res.pivot(index="model", columns="fold", values="wape_score")[["C", "E", "A", "B"]]
    pv["среднее"] = pv.mean(axis=1)
    print(pv.sort_values("среднее", ascending=False).round(4).to_string())
    bias = res.pivot(index="model", columns="fold", values="bias_pct")[["C", "E", "A", "B"]]
    print("\nсмещение, %:\n", bias.round(1).to_string())


if __name__ == "__main__":
    main()
