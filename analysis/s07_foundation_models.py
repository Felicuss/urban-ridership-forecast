"""Zero-shot foundation-модели на тех же фолдах, что и s06: Chronos-2, TimesFM 3.0, t0-beta.

Почасовой ряд на маршрут, контекст - вся история до origin, горизонт - весь фолд
(до 1488 часов). Точечный прогноз - квантиль 0.5 (оптимум для L1/WAPE).
Будущие ковариаты: нерабочий день и праздник (0/1) на контекст + горизонт.
Нужна группа зависимостей fm: uv sync --extra fm
Запуск: uv run python analysis/s07_foundation_models.py
"""

import sys
import time

import numpy as np
import pandas as pd
import torch

from common import ACTIVE_ROUTES, DATA, TABLES, wape_score
from s06_backtest import FOLDS, load_frame

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
COVARIATES = ["is_day_off", "is_holiday"]


def series_arrays(full: pd.DataFrame, origin: pd.Timestamp, end: pd.Timestamp):
    """Контекст [routes, T], ковариаты [routes, F, T + H], ключи горизонта."""
    ctx = full[full.date <= origin]
    fut = full[(full.date > origin) & (full.date <= end)]
    y = np.stack([ctx[ctx.route == r].sort_values("ts")["boardings"].to_numpy(float) for r in ACTIVE_ROUTES])
    both = pd.concat([ctx, fut])
    cov = np.stack([
        both[both.route == r].sort_values("ts")[COVARIATES].astype(float).to_numpy().T for r in ACTIVE_ROUTES
    ])
    horizon = fut.ts.nunique()
    return y, cov, horizon


def run_chronos(full, origin, end, use_cov: bool) -> np.ndarray:
    from chronos import Chronos2Pipeline

    if "chronos" not in _cache:
        _cache["chronos"] = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map=DEVICE)
    pipe = _cache["chronos"]
    ctx = full[(full.date <= origin) & full.route.isin(ACTIVE_ROUTES)]
    fut = full[(full.date > origin) & (full.date <= end) & full.route.isin(ACTIVE_ROUTES)]
    cols = ["route", "ts", "boardings"] + (COVARIATES if use_cov else [])
    context_df = ctx[cols].rename(columns={"route": "id", "ts": "timestamp", "boardings": "target"})
    context_df[COVARIATES if use_cov else []] = context_df[COVARIATES if use_cov else []].astype(float)
    future_df = None
    if use_cov:
        future_df = fut[["route", "ts"] + COVARIATES].rename(columns={"route": "id", "ts": "timestamp"})
        future_df[COVARIATES] = future_df[COVARIATES].astype(float)
    horizon = fut.ts.nunique()
    pred = pipe.predict_df(
        context_df, future_df=future_df, prediction_length=horizon, quantile_levels=[0.5],
        id_column="id", timestamp_column="timestamp", target="target", batch_size=4,
    )
    pred = pred.rename(columns={"id": "route", "timestamp": "ts"})
    return pred[["route", "ts", "0.5"]].rename(columns={"0.5": "pred"})


def run_timesfm(full, origin, end, use_cov: bool) -> pd.DataFrame:
    from timesfm3 import TimesFM3Forecaster

    if "timesfm" not in _cache:
        _cache["timesfm"] = TimesFM3Forecaster.from_pretrained(
            "google/timesfm-3.0-pytorch", device=DEVICE, per_core_batch_size=1)
    model = _cache["timesfm"]
    y, cov, horizon = series_arrays(full, origin, end)
    outs = model.predict_batch(
        contexts=[row for row in y], horizon=horizon,
        past_future_covariates=[c for c in cov] if use_cov else None,
    )
    preds = np.stack([o.forecast for o in outs])
    return _to_frame(full, origin, end, preds)


def run_t0(full, origin, end, use_cov: bool) -> pd.DataFrame:
    from t0 import T0Forecaster

    if "t0" not in _cache:
        _cache["t0"] = T0Forecaster.from_pretrained("theforecastingcompany/t0-beta").eval().to(DEVICE)
    model = _cache["t0"]
    y, cov, horizon = series_arrays(full, origin, end)
    fc = model.predict(
        y.astype(np.float32), horizon=horizon, quantile_levels=(0.5,),
        future_covariates=cov.astype(np.float32) if use_cov else None,
    )
    preds = fc.median.detach().cpu().numpy()
    return _to_frame(full, origin, end, preds)


def _to_frame(full, origin, end, preds: np.ndarray) -> pd.DataFrame:
    fut = full[(full.date > origin) & (full.date <= end)]
    ts = np.sort(fut.ts.unique())
    parts = [pd.DataFrame({"route": r, "ts": ts, "pred": preds[i][: len(ts)]}) for i, r in enumerate(ACTIVE_ROUTES)]
    return pd.concat(parts, ignore_index=True)


_cache: dict = {}
RUNNERS = {
    "Chronos-2": (run_chronos, False),
    "Chronos-2 + календарь": (run_chronos, True),
    "TimesFM 3.0": (run_timesfm, False),
    "TimesFM 3.0 + календарь": (run_timesfm, True),
    "t0-beta": (run_t0, False),
    "t0-beta + календарь": (run_t0, True),
}


def main() -> None:
    wanted = sys.argv[1:] or list(RUNNERS)
    full = load_frame()
    scores, preds = [], []
    for fold in FOLDS:
        origin, end = pd.Timestamp(fold.origin), pd.Timestamp(fold.end)
        grid = full[(full.date > origin) & (full.date <= end)][["route", "ts", "boardings"]]
        for name, (fn, use_cov) in RUNNERS.items():
            if not any(w in name for w in wanted):
                continue
            t0_ = time.time()
            try:
                p = fn(full, origin, end, use_cov)
            except Exception as exc:  # фиксируем падение модели в таблице, а не роняем весь прогон
                print(f"{fold.name} {name}: FAILED {type(exc).__name__}: {exc}")
                scores.append({"fold": fold.name, "model": name, "wape_score": np.nan, "error": str(exc)[:200]})
                continue
            g = grid.merge(p, on=["route", "ts"], how="left")
            g["pred"] = g["pred"].fillna(0).clip(lower=0)  # маршрут 5 и отрицательные значения -> 0
            s = wape_score(g.boardings, g.pred)
            bias = (g.pred.sum() / g.boardings.sum() - 1) * 100
            secs = time.time() - t0_
            print(f"{fold.name:34s} {name:26s} {s:.4f} bias {bias:+.1f}% {secs:.0f}s", flush=True)
            scores.append({"fold": fold.name, "model": name, "wape_score": s, "bias_pct": bias, "seconds": secs})
            preds.append(g.assign(fold=fold.name, model=name)[["fold", "model", "route", "ts", "pred"]])
    res = pd.DataFrame(scores)
    tag = "_".join(w.split()[0].replace("-", "").lower() for w in wanted) if sys.argv[1:] else "all"
    res.to_csv(TABLES / f"backtest_fm_{tag}.csv", index=False, float_format="%.4f")
    pd.concat(preds).to_parquet(DATA / f"fm_backtest_preds_{tag}.parquet")
    print(res.pivot(index="model", columns="fold", values="wape_score").round(4).to_string())


if __name__ == "__main__":
    main()
