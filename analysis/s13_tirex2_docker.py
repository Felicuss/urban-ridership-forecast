"""TiRex-2 на тех же фолдах, что и s07, но инференс идёт в Docker с GPU.

TiRex-2 на Windows требует MSVC даже для CPU, поэтому модель крутится в официальном
образе ghcr.io/nx-ai/tirex2-gpu (CUDA 12.8, nvcc для сборки ядра FlashRNN), а данные
передаются через data/fm_io. Все шаги сразу делает analysis/docker/run_tirex2.ps1:
    uv run python analysis/s13_tirex2_docker.py export
    docker run --rm --gpus all -e HF_HOME=/work/hf-cache -v <repo>/data/fm_io:/work
        -v <repo>/analysis/docker:/code:ro ghcr.io/nx-ai/tirex2-gpu:latest python /code/tirex2_forecast.py
    uv run python analysis/s13_tirex2_docker.py collect
"""

import sys

import numpy as np
import pandas as pd

from common import ACTIVE_ROUTES, DATA, TABLES, wape_score
from s06_backtest import FOLDS, load_frame
from s07_foundation_models import series_arrays

IO = DATA / "fm_io"
FOLD_KEYS = {f.name: f.name.split(":")[0] for f in FOLDS}  # "C", "E", "A", "B"
VARIANT_NAMES = {
    "uni": "TiRex-2",
    "uni_cov": "TiRex-2 + календарь",
    "multi_cov": "TiRex-2 многомерный + календарь",
}


def final_frame() -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    """История + сетка ноября-декабря с ковариатами, как в s10."""
    from s10_forecast import forecast_grid, load_history

    hist, grid = load_history(), forecast_grid()
    full = pd.concat([hist, grid.assign(boardings=np.nan)], ignore_index=True)
    full["is_day_off"] = full["is_day_off"].astype(bool)
    return full, hist.date.max(), grid.date.max()


def export() -> None:
    (IO / "inputs").mkdir(parents=True, exist_ok=True)
    full = load_frame()
    jobs = [(FOLD_KEYS[f.name], full, pd.Timestamp(f.origin), pd.Timestamp(f.end)) for f in FOLDS]
    jobs.append(("final", *final_frame()))
    for key, frame, origin, end in jobs:
        y, cov, horizon = series_arrays(frame, origin, end)
        np.savez(IO / "inputs" / f"{key}.npz", y=y.astype(np.float32), cov=cov.astype(np.float32), horizon=horizon)
        print(f"{key}: y={y.shape} cov={cov.shape} horizon={horizon}")


def to_frame(frame: pd.DataFrame, origin, end, pred: np.ndarray) -> pd.DataFrame:
    fut = frame[(frame.date > origin) & (frame.date <= end)]
    ts = np.sort(fut.ts.unique())
    parts = [pd.DataFrame({"route": r, "ts": ts, "pred": pred[i][: len(ts)]}) for i, r in enumerate(ACTIVE_ROUTES)]
    return pd.concat(parts, ignore_index=True)


def collect() -> None:
    full = load_frame()
    rows, preds = [], []
    for fold in FOLDS:
        origin, end = pd.Timestamp(fold.origin), pd.Timestamp(fold.end)
        grid = full[(full.date > origin) & (full.date <= end)][["route", "ts", "boardings"]]
        for variant, name in VARIANT_NAMES.items():
            path = IO / "outputs" / f"{FOLD_KEYS[fold.name]}__{variant}.npz"
            if not path.exists():
                print(f"нет {path.name}")
                continue
            p = to_frame(full, origin, end, np.load(path)["pred"])
            g = grid.merge(p, on=["route", "ts"], how="left")
            g["pred"] = g["pred"].fillna(0).clip(lower=0)
            s = wape_score(g.boardings, g.pred)
            bias = (g.pred.sum() / g.boardings.sum() - 1) * 100
            rows.append({"fold": fold.name, "model": name, "wape_score": s, "bias_pct": bias})
            preds.append(g.assign(fold=fold.name, model=name)[["fold", "model", "route", "ts", "pred"]])
            print(f"{fold.name:34s} {name:34s} {s:.4f} bias {bias:+.1f}%")
    res = pd.DataFrame(rows)
    res.to_csv(TABLES / "backtest_fm_tirex2.csv", index=False, float_format="%.4f")
    pd.concat(preds).to_parquet(DATA / "fm_backtest_preds_tirex2.parquet")
    pv = res.pivot(index="model", columns="fold", values="wape_score")[[f.name for f in FOLDS]]
    pv["среднее"] = pv.mean(axis=1)
    print(pv.round(4).to_string())

    frame, origin, end = final_frame()
    finals = []
    for variant in VARIANT_NAMES:
        path = IO / "outputs" / f"final__{variant}.npz"
        if path.exists():
            finals.append(to_frame(frame, origin, end, np.load(path)["pred"]).assign(model=f"tirex2_{variant}"))
    if finals:
        out = pd.concat(finals, ignore_index=True)
        out["pred"] = out["pred"].clip(lower=0)
        out.to_parquet(DATA / "fm_forecast_novdec_tirex2.parquet")


if __name__ == "__main__":
    {"export": export, "collect": collect}[sys.argv[1]]()
