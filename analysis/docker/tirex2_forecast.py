"""Прогноз TiRex-2 внутри Docker-образа ghcr.io/nx-ai/tirex2-gpu (только numpy + tirex2).

Читает /work/inputs/*.npz (y [routes, T], cov [routes, F, T + H], horizon), пишет
/work/outputs/<имя>__<вариант>.npz с медианой [routes, H]. Варианты:
- uni: каждый маршрут отдельно, без ковариат;
- uni_cov: каждый маршрут отдельно, будущие ковариаты «нерабочий день» и «праздник»;
- multi_cov: все маршруты одной многомерной целью + те же ковариаты.
Запуск: см. docs/analysis/README.md, п. 4.4.
"""

import sys
import time
from pathlib import Path

import numpy as np
import torch
from tirex2 import TimeseriesType, load_model

WORK = Path("/work")
MEDIAN_IDX = 4  # квантили 0.1 … 0.9, индекс 4 = 0.5


def forecast_once(model, y: np.ndarray, cov: np.ndarray, horizon: int, variant: str) -> np.ndarray:
    """Один вызов модели. TiRex-2 обрезает горизонт до своего максимума (320 шагов),
    поэтому длина ответа может быть меньше запрошенной."""
    if variant == "multi_cov":
        ts = TimeseriesType(target=torch.tensor(y, dtype=torch.float32), past_covariates=None,
                            future_covariates=torch.tensor(cov[0], dtype=torch.float32))
        out = model.forecast([ts], prediction_length=horizon, output_type="numpy")[0]
        return out[:, MEDIAN_IDX, :]
    series = []
    for i in range(y.shape[0]):
        fut = torch.tensor(cov[i], dtype=torch.float32) if variant == "uni_cov" else None
        series.append(TimeseriesType(target=torch.tensor(y[i : i + 1], dtype=torch.float32),
                                     past_covariates=None, future_covariates=fut))
    outs = model.forecast(series, prediction_length=horizon, output_type="numpy")
    return np.stack([o[0, MEDIAN_IDX, :] for o in outs])


def run_variant(model, y: np.ndarray, cov: np.ndarray, horizon: int, variant: str) -> tuple[np.ndarray, int]:
    """Авторегрессионная раскатка: медиану каждого куска дописываем в контекст и просим следующий."""
    ctx, parts, done = y.copy(), [], 0
    while done < horizon:
        step = horizon - done
        pred = forecast_once(model, ctx, cov[..., : ctx.shape[1] + step], step, variant)
        if pred.shape[1] == 0:
            raise RuntimeError("модель вернула пустой прогноз")
        pred = np.clip(pred, 0, None)  # посадки не бывают отрицательными
        parts.append(pred)
        ctx = np.concatenate([ctx, pred], axis=1)
        done += pred.shape[1]
    return np.concatenate(parts, axis=1)[:, :horizon], len(parts)


def main() -> None:
    variants = sys.argv[1:] or ["uni", "uni_cov", "multi_cov"]
    print("torch", torch.__version__, "cuda", torch.version.cuda, "available", torch.cuda.is_available(),
          torch.cuda.get_device_name(0) if torch.cuda.is_available() else "-", flush=True)
    model = load_model("NX-AI/TiRex-2", device="cuda")
    out_dir = WORK / "outputs"
    out_dir.mkdir(exist_ok=True)
    for path in sorted((WORK / "inputs").glob("*.npz")):
        data = np.load(path)
        y, cov, horizon = data["y"], data["cov"], int(data["horizon"])
        for variant in variants:
            t0 = time.time()
            try:
                pred, chunks = run_variant(model, y, cov, horizon, variant)
            except Exception as exc:  # фиксируем причину и идём дальше, чтобы не терять остальные фолды
                print(f"{path.stem} {variant}: FAILED {type(exc).__name__}: {exc}", flush=True)
                continue
            np.savez(out_dir / f"{path.stem}__{variant}.npz", pred=pred)
            print(f"{path.stem} {variant}: shape={pred.shape} chunks={chunks} {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
