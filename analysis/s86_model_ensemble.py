"""Ансамбль оценённых моделей разной архитектуры поверх v11.

v11 (сезонная цепочка), v8 (нейросеть JointDayNet), v9 (графовая модель режимов) и s85 (уровень × форма)
при близких скорах расходятся на 2-3 % объёма по ячейкам, то есть ошибаются в разных местах. WAPE выпуклый,
поэтому скор смеси не ниже взвешенного среднего скоров её частей, а при несовпадающих ошибках выше.
Нули v11 (часы вне работы маршрута, бесплатный проезд 31.12, маршрут 5 до запуска) сохраняются: это правила.

Запуск: PYTHONUTF8=1 uv run python analysis/s86_model_ensemble.py
"""

import hashlib
import json

import numpy as np
import pandas as pd

from common import ROOT

FORECASTS = ROOT / "forecasts"
MODELS = {"v11": "submission_seasonal_daily_v11.csv", "v8": "submission_joint_day_v8.csv",
          "v9": "submission_architecture_v9.csv", "s85": "submission_level_shape_v12.csv"}
BLENDS = {
    "submission_ensemble_e1.csv": {"v11": 1 / 3, "v8": 1 / 3, "v9": 1 / 3},
    "submission_ensemble_e2.csv": {"v11": 0.5, "v8": 0.25, "v9": 0.25},
}


def load() -> tuple[pd.DataFrame, dict[str, np.ndarray], dict[str, float]]:
    scores = {r["file"]: r["leaderboard_score"] for r in
              json.loads((FORECASTS / "leaderboard_results.json").read_text(encoding="utf-8"))}
    frames = {k: pd.read_csv(FORECASTS / f, sep=";").sort_values(["route", "date", "hour"], ignore_index=True)
              for k, f in MODELS.items()}
    grid = frames["v11"][["route", "date", "hour"]]
    for k, f in frames.items():
        assert f[["route", "date", "hour"]].equals(grid), k
    return grid, {k: f.prediction.to_numpy(float) for k, f in frames.items()}, {k: scores[f] for k, f in MODELS.items()}


def main() -> None:
    grid, preds, scores = load()
    zero = preds["v11"] == 0
    for name, weights in BLENDS.items():
        blend = sum(w * preds[k] for k, w in weights.items())
        blend = np.where(zero, 0.0, blend)
        out = grid.assign(prediction=np.rint(blend).astype("int64"))
        path = FORECASTS / name
        out.to_csv(path, sep=";", index=False)
        floor = sum(w * scores[k] for k, w in weights.items())
        meta = dict(file=name, status="unscored", sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    weights=weights, floor_from_convexity=round(floor, 5),
                    diff_to_v11=round(float(np.abs(out.prediction - preds["v11"]).sum() / preds["v11"].sum()), 4),
                    script="analysis/s86_model_ensemble.py")
        path.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(name, weights, "пол по выпуклости", round(floor, 5), "отличие от v11", meta["diff_to_v11"])


if __name__ == "__main__":
    main()
