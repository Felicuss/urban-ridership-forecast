"""Коридор прогноза, качество по бэктесту и горизонт «год» для сервиса.

Коридор p10-p90. Схема по умолчанию (профиль 2 нед × сезонность городского трамвая прошлых лет,
как в s30 и s34) прогоняется на пяти фолдах бэктеста по 1-2 месяца. Для каждой детализации берём
квантили 10 % и 90 % от log((y + 1) / (p + 1)): по часам отдельно для каждого часа суток, по суткам
для каждого типа дня, по месяцам одним числом. Покрытие проверяем честно: квантили по четырём
фолдам, покрытие на пятом.

Год. Ноябрь и декабрь 2025 - суммы почасового прогноза. Январь-октябрь 2026 - уровень маршрута,
приведённый к октябрю, × сезонный индекс городского трамвая (медиана 2022-2024, амплитуда 0.83).
Коридор ±12 %: на реальных месяцах индекс ошибался до 12.6 % (docs/research/review_round1.md, п. 7.4).
"""

import numpy as np
import pandas as pd

from common import ROOT, wape_score
from models import ProfileConfig, profile_forecast
from s06_backtest import load_frame
from s31_weather_probe import CV_FOLDS
from s34_traffic_probe import city_tram_monthly

PAST_YEARS = [2019, 2022, 2023, 2024]  # как в s30 и s34
YEAR_BASE_YEARS = [2022, 2023, 2024]  # октябрь года Y -> месяцы года Y + 1, без ковидных 2020-2021
AMPLITUDE = 0.83
YEAR_CORRIDOR = 0.12
QUANTILES = (0.1, 0.9)


def backtest_frame() -> pd.DataFrame:
    """Факт и прогноз схемы по умолчанию на всех фолдах, по часам."""
    full = load_frame()
    lr = city_tram_monthly().set_index(["year", "month"]).lr
    parts = []
    for fold in CV_FOLDS:
        origin = pd.Timestamp(fold.origin)
        history = full[full.date <= origin]
        grid = full[(full.date > origin) & (full.date <= pd.Timestamp(fold.end))].reset_index(drop=True)
        base = profile_forecast(history, grid.drop(columns="boardings"), origin, ProfileConfig(weeks=2))
        seasonal = AMPLITUDE * grid.date.dt.month.map(
            lambda m: np.median([lr[(y, m)] - lr[(y, origin.month)] for y in PAST_YEARS])).to_numpy()
        parts.append(grid[["route", "date", "hour", "kind"]].assign(
            fold=fold.name[0], y=grid.boardings.to_numpy(), p=base * np.exp(seasonal)))
    return pd.concat(parts, ignore_index=True)


def by_granularity(bt: pd.DataFrame) -> dict[str, tuple[pd.DataFrame, str | None]]:
    """Таблицы факт/прогноз на трёх детализациях и признак, по которому считаем отдельные квантили."""
    day = bt.groupby(["fold", "route", "date", "kind"], as_index=False)[["y", "p"]].sum()
    month = (bt.assign(month=bt.date.dt.month).groupby(["fold", "route", "month"], as_index=False)[["y", "p"]].sum())
    return {"hour": (bt, "hour"), "day": (day, "kind"), "month": (month.assign(all="all"), "all")}


def _quantiles(df: pd.DataFrame, key: str) -> dict:
    r = np.log((df.y + 1) / (df.p + 1))
    q = r.groupby(df[key]).quantile(list(QUANTILES)).unstack()
    return {str(k): [round(float(np.exp(q.loc[k, QUANTILES[0]])), 4), round(float(np.exp(q.loc[k, QUANTILES[1]])), 4)]
            for k in q.index}


def _coverage(df: pd.DataFrame, key: str) -> float:
    """Доля фактов внутри коридора, квантили которого посчитаны без этого фолда.

    Коридор строим так же, как сервис: p10 = p × f10, p90 = p × f90.
    """
    inside = []
    for fold in sorted(df.fold.unique()):
        test, train = df[df.fold == fold], df[df.fold != fold]
        q = _quantiles(train, key)
        keys = test[key].astype(str)
        lo = keys.map(lambda k: q[k][0]) * test.p
        hi = keys.map(lambda k: q[k][1]) * test.p
        inside.append(((test.y >= lo) & (test.y <= hi)).mean())
    return round(float(np.mean(inside)), 3)


def intervals_and_metrics(bt: pd.DataFrame) -> tuple[dict, dict]:
    intervals, coverage, scores = {}, {}, {}
    for gran, (df, key) in by_granularity(bt).items():
        intervals[gran] = {"by": key, "factors": _quantiles(df, key)}
        coverage[gran] = _coverage(df, key)
        scores[gran] = {fold: round(wape_score(d.y, d.p), 4) for fold, d in df.groupby("fold")}
    intervals["note"] = ("p10 = p50 × factors[0], p90 = p50 × factors[1]; квантили log((y+1)/(p+1)) по пяти фолдам "
                         "бэктеста, для нуля в прогнозе коридор нулевой")
    metrics = {"scheme": "профиль 2 нед × сезонность городского трамвая прошлых лет (s30, s34)",
               "folds": {f.name[0]: f.name for f in CV_FOLDS}, "wape_score": scores,
               "interval_nominal": QUANTILES[1] - QUANTILES[0], "interval_coverage_leave_one_fold_out": coverage}
    return intervals, metrics


def seasonal_index() -> pd.Series:
    """Посадки городского трамвая в сутки в месяце Y+1 (или Y) к октябрю Y, медиана по базовым годам."""
    city = pd.read_csv(ROOT / "external" / "datamos_62521_monthly_ridership.csv")
    tram = city[city.transport == "Трамвай"].pivot(index="year", columns="month", values="per_day")
    ratios = {m: np.median([tram.loc[y, m] / tram.loc[y, 10] for y in PAST_YEARS]) for m in (11, 12)}
    ratios |= {m: np.median([tram.loc[y + 1, m] / tram.loc[y, 10] for y in YEAR_BASE_YEARS]) for m in range(1, 11)}
    return pd.Series({m: 1 + AMPLITUDE * (r - 1) for m, r in ratios.items()})


def index_check(index: pd.Series) -> dict:
    """Насколько сезонный индекс угадал городской трамвай в ноябре 2025 - августе 2026 (данные постфактум)."""
    city = pd.read_csv(ROOT / "external" / "datamos_62521_monthly_ridership.csv")
    tram = city[city.transport == "Трамвай"].set_index(["year", "month"]).per_day
    rows = []
    for year, month in [(2025, 11), (2025, 12), *[(2026, m) for m in range(1, 11)]]:
        if (year, month) not in tram.index:
            continue
        raw = (index[month] - 1) / AMPLITUDE + 1  # индекс без амплитуды наших маршрутов
        fact = tram[(year, month)] / tram[(2025, 10)]
        rows.append(raw / fact - 1)
    err = np.array(rows)
    return {"months": len(err), "mape_pct": round(float(np.abs(err).mean() * 100), 2),
            "mean_error_pct": round(float(err.mean() * 100), 2), "max_abs_error_pct": round(float(np.abs(err).max() * 100), 2)}


def year_forecast(comp: pd.DataFrame, prediction: np.ndarray) -> tuple[pd.DataFrame, dict]:
    """Помесячный прогноз ноябрь 2025 - октябрь 2026 по маршрутам."""
    index = seasonal_index()
    fc = comp[["route", "date"]].assign(p=prediction, month=pd.to_datetime(comp.date).dt.month)
    novdec = fc.groupby(["route", "month"]).p.sum()
    days = {11: 30, 12: 31}
    rows = []
    for route in sorted(fc.route.unique()):
        if route == 5:  # запущен 16.12: уровень по полным будням второй половины декабря
            d = fc[(fc.route == 5) & fc.date.between("2025-12-17", "2025-12-30")].groupby("date").p.sum()
            level = d.mean() / index[12]
        else:
            level = sum(novdec[(route, m)] for m in (11, 12)) / sum(days[m] * index[m] for m in (11, 12))
        for year, month in [(2025, 11), (2025, 12), *[(2026, m) for m in range(1, 11)]]:
            if (year, month) in [(2025, 11), (2025, 12)]:
                p50, method = float(novdec[(route, month)]), "hourly"
            else:
                p50, method = level * index[month] * pd.Period(f"{year}-{month:02d}").days_in_month, "seasonal_index"
            rows.append({"route": int(route), "month": f"{year}-{month:02d}", "p50": round(p50),
                         "p10": round(p50 * (1 - YEAR_CORRIDOR)), "p90": round(p50 * (1 + YEAR_CORRIDOR)),
                         "method": method})
    return pd.DataFrame(rows), {"seasonal_index": {int(k): round(float(v), 4) for k, v in index.items()},
                                "corridor": YEAR_CORRIDOR, "index_check_city_tram": index_check(index)}
