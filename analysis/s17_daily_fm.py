"""Foundation-модели на дневных суммах маршрута × форма суток из профиля.

Почасовой ряд даёт горизонт 1464 шага, дневной только 31-62, в пределах одного прохода
у всех моделей. Прогноз часа = прогноз суток модели × доля часа в сутках из профиля
за 2 недели (для праздника форма воскресенья). Ковариаты: нерабочий день и праздник.
Нужна группа fm: uv sync --extra fm
Запуск: uv run python analysis/s17_daily_fm.py
"""

import time

import numpy as np
import pandas as pd
import torch

from common import ACTIVE_ROUTES, DATA, TABLES, wape_score
from models import ProfileConfig, profile_forecast
from s06_backtest import FOLDS, load_frame

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
COVS = ["is_day_off", "is_holiday"]
_cache: dict = {}


def daily_frame(full: pd.DataFrame) -> pd.DataFrame:
    d = full[full.route.isin(ACTIVE_ROUTES)].groupby(["route", "date"], as_index=False).agg(
        boardings=("boardings", "sum"), is_day_off=("is_day_off", "first"), is_holiday=("is_holiday", "first"))
    d[COVS] = d[COVS].astype(float)
    return d


def arrays(d: pd.DataFrame, origin, end):
    ctx = d[d.date <= origin]
    both = d[d.date <= end]
    y = np.stack([ctx[ctx.route == r].sort_values("date").boardings.to_numpy(float) for r in ACTIVE_ROUTES])
    cov = np.stack([both[both.route == r].sort_values("date")[COVS].to_numpy(float).T for r in ACTIVE_ROUTES])
    return y, cov, int((end - origin).days)


def chronos(d, origin, end) -> np.ndarray:
    from chronos import Chronos2Pipeline

    if "chronos" not in _cache:
        _cache["chronos"] = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map=DEVICE)
    ctx = d[d.date <= origin].rename(columns={"route": "id", "date": "timestamp", "boardings": "target"})
    fut = d[(d.date > origin) & (d.date <= end)].rename(columns={"route": "id", "date": "timestamp"})
    h = int((end - origin).days)
    pred = _cache["chronos"].predict_df(
        ctx[["id", "timestamp", "target", *COVS]], future_df=fut[["id", "timestamp", *COVS]],
        prediction_length=h, quantile_levels=[0.5], id_column="id", timestamp_column="timestamp", target="target",
    )
    return np.stack([pred[pred.id == r].sort_values("timestamp")["0.5"].to_numpy() for r in ACTIVE_ROUTES])


def timesfm(d, origin, end) -> np.ndarray:
    from timesfm3 import TimesFM3Forecaster

    if "timesfm" not in _cache:
        _cache["timesfm"] = TimesFM3Forecaster.from_pretrained("google/timesfm-3.0-pytorch", device=DEVICE,
                                                               per_core_batch_size=1)
    y, cov, h = arrays(d, origin, end)
    outs = _cache["timesfm"].predict_batch(contexts=list(y), horizon=h, past_future_covariates=list(cov))
    return np.stack([o.forecast for o in outs])


def t0(d, origin, end) -> np.ndarray:
    from t0 import T0Forecaster

    if "t0" not in _cache:
        _cache["t0"] = T0Forecaster.from_pretrained("theforecastingcompany/t0-beta").eval().to(DEVICE)
    y, cov, h = arrays(d, origin, end)
    fc = _cache["t0"].predict(y.astype(np.float32), horizon=h, quantile_levels=(0.5,),
                              future_covariates=cov.astype(np.float32))
    return fc.median.detach().cpu().numpy()


MODELS = {"Chronos-2 дневной": chronos, "t0-beta дневной": t0, "TimesFM 3.0 дневной": timesfm}


def to_hourly(grid: pd.DataFrame, shape_pred: np.ndarray, daily_pred: np.ndarray, origin) -> np.ndarray:
    """Раскладываем прогноз суток по часам долями профиля (маршрут 5 и нули остаются нулями)."""
    g = grid[["route", "date"]].assign(p=shape_pred)
    day_sum = g.groupby(["route", "date"])["p"].transform("sum").to_numpy()
    share = np.where(day_sum > 0, shape_pred / np.where(day_sum > 0, day_sum, 1), 0)
    dates = np.sort(grid.date.unique())
    lookup = {(r, dt): daily_pred[i][j] for i, r in enumerate(ACTIVE_ROUTES) for j, dt in enumerate(dates)}
    daily = np.array([lookup.get((r, dt), 0.0) for r, dt in zip(grid.route, grid.date, strict=True)])
    return share * np.clip(daily, 0, None)


def main() -> None:
    pd.set_option("display.width", 220)
    full = load_frame()
    d = daily_frame(full)
    rows, preds = [], []
    for fold in FOLDS:
        origin, end = pd.Timestamp(fold.origin), pd.Timestamp(fold.end)
        grid = full[(full.date > origin) & (full.date <= end)].reset_index(drop=True)
        hist = full[full.date <= origin]
        prof = profile_forecast(hist, grid.drop(columns="boardings"), origin, ProfileConfig(weeks=2))
        rows.append({"fold": fold.name[:1], "model": "профиль 2 нед", "wape_score": wape_score(grid.boardings, prof)})
        members = {"профиль 2 нед": prof}
        for name, fn in MODELS.items():
            t = time.time()
            p = to_hourly(grid, prof, fn(d, origin, end), origin)
            members[name] = p
            rows.append({"fold": fold.name[:1], "model": name, "wape_score": wape_score(grid.boardings, p),
                         "bias_pct": (p.sum() / grid.boardings.sum() - 1) * 100, "seconds": time.time() - t})
            print(f"{fold.name[:1]} {name:22s} {rows[-1]['wape_score']:.4f} bias {rows[-1]['bias_pct']:+.1f}%",
                  flush=True)
        combos = {
            "профиль + Chronos-2 + t0 (дневные)": ["профиль 2 нед", "Chronos-2 дневной", "t0-beta дневной"],
            "Chronos-2 + t0 (дневные)": ["Chronos-2 дневной", "t0-beta дневной"],
            "профиль + три дневных FM": [
                "профиль 2 нед", "Chronos-2 дневной", "t0-beta дневной", "TimesFM 3.0 дневной",
            ],
        }
        for name, cols in combos.items():
            p = np.mean([members[c] for c in cols], axis=0)
            rows.append({"fold": fold.name[:1], "model": name, "wape_score": wape_score(grid.boardings, p)})
        preds.append(grid[["route", "ts"]].assign(fold=fold.name, **{k: v for k, v in members.items()}))
    res = pd.DataFrame(rows)
    res.to_csv(TABLES / "exp2_daily_fm.csv", index=False, float_format="%.4f")
    pd.concat(preds).to_parquet(DATA / "fm_daily_backtest_preds.parquet")
    pv = res.pivot_table(index="model", columns="fold", values="wape_score")[["C", "E", "A", "B"]]
    pv["среднее"] = pv.mean(axis=1)
    print(pv.sort_values("среднее", ascending=False).round(4).to_string())


if __name__ == "__main__":
    main()
