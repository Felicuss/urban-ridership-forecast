"""Раунд 2: профиль как «дневной уровень × форма суток» и что его улучшает.

Проверяем на тех же 4 фолдах, что и s06:
- окно уровня (1-4 недели) отдельно от окна формы суток (4-12 недель);
- уровень будней по дням недели при общей форме суток;
- очистку истории от аномальных дней (перекрытия, сбои) перед расчётом;
- затухающий тренд недельного уровня;
- оптимальный множитель уровня на фолде (сколько ошибки даёт смещение).
Запуск: uv run python analysis/s14_profile_experiments.py
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from common import TABLES, wape_score
from models import HOLIDAY_TO_SUNDAY, WORKING_SATURDAY_TO_WORKDAY
from s06_backtest import FOLDS, load_frame

ANOMALY_THRESHOLD = 0.35


@dataclass(frozen=True)
class LevelShape:
    level_weeks: int = 2
    shape_weeks: int = 8
    level_by_dow: bool = False
    clean: bool = False
    trend_damping: float = 0.0  # 0 - без тренда; 0.8-0.95 - затухание за неделю
    level_stat: str = "median"


def mark_anomalies(hist: pd.DataFrame) -> pd.Series:
    """Флаг маршруто-дня: сутки отклоняются от медианы того же типа дня в окне ±21 день больше чем на 35 %."""
    daily = hist.groupby(["route", "date", "kind"], as_index=False)["boardings"].sum()
    daily = daily[daily.boardings > 0].sort_values("date")
    flags = []
    for _, g in daily.groupby(["route", "kind"]):
        s = g.set_index("date")["boardings"].astype(float)
        exp = s.rolling("43D", center=True, min_periods=3).median()
        ratio = s / exp
        flags.append(g.assign(anomaly=((ratio - 1).abs() > ANOMALY_THRESHOLD).to_numpy()))
    out = pd.concat(flags)[["route", "date", "anomaly"]]
    return out.set_index(["route", "date"])["anomaly"]


def forecast(hist: pd.DataFrame, grid: pd.DataFrame, origin: pd.Timestamp, cfg: LevelShape) -> np.ndarray:
    h = hist[~hist.is_holiday].copy()
    if cfg.clean:
        anom = mark_anomalies(h)
        key = pd.MultiIndex.from_arrays([h.route, h.date])
        is_anom = anom.reindex(key).fillna(False).astype(bool).to_numpy()
        h = h[~is_anom]
    lvl_h = h[h.date > origin - pd.Timedelta(weeks=cfg.level_weeks)]
    shp_h = h[h.date > origin - pd.Timedelta(weeks=cfg.shape_weeks)]

    # форма суток: доли часов в сумме за окно (взвешено объёмом, устойчивее среднего долей)
    by_hour = shp_h.groupby(["route", "kind", "hour"])["boardings"].sum()
    shape = by_hour / by_hour.groupby(level=[0, 1]).transform("sum")

    daily = lvl_h.groupby(["route", "date", "kind", "dow"], as_index=False)["boardings"].sum()
    level = daily.groupby(["route", "kind"])["boardings"].agg(cfg.level_stat)
    g_level = level.reindex(pd.MultiIndex.from_arrays([grid.route, grid.kind])).to_numpy(dtype=float)
    if cfg.level_by_dow:
        wd = daily[daily.kind == "workday"]
        by_dow = wd.groupby(["route", "dow"])["boardings"].agg(cfg.level_stat)
        dow_level = by_dow.reindex(pd.MultiIndex.from_arrays([grid.route, grid.dow])).to_numpy(dtype=float)
        use = (grid.kind == "workday").to_numpy() & ~np.isnan(dow_level)
        g_level = np.where(use, dow_level, g_level)

    if cfg.trend_damping > 0:
        wk = h[(h.kind == "workday") & (h.date > origin - pd.Timedelta(weeks=8))]
        weekly = wk.groupby(["route", wk.date.dt.to_period("W")])["boardings"].sum()
        slopes = {}
        for route, s in weekly.groupby(level=0):
            y = np.log(s.to_numpy() + 1)
            slopes[route] = np.polyfit(np.arange(len(y)), y, 1)[0] if len(y) >= 4 else 0.0
        weeks_ahead = ((grid.date - origin).dt.days / 7).to_numpy()
        phi = cfg.trend_damping
        damped = (1 - phi ** weeks_ahead) / (1 - phi) * phi  # сумма phi^1..phi^k
        g_slope = grid.route.map(slopes).fillna(0).to_numpy()
        g_level = g_level * np.exp(g_slope * damped)

    g_shape = shape.reindex(pd.MultiIndex.from_arrays([grid.route, grid.kind, grid.hour])).to_numpy(dtype=float)
    pred = np.nan_to_num(g_level * g_shape)
    pred *= np.where(grid.is_holiday & (grid.dow < 5), HOLIDAY_TO_SUNDAY, 1.0)
    pred *= np.where((grid.dow == 5) & (grid.day_type == "workday"), WORKING_SATURDAY_TO_WORKDAY, 1.0)
    return pred


def best_scale(y: np.ndarray, p: np.ndarray) -> tuple[float, float]:
    """Множитель k, минимизирующий Σ|y - k·p|: взвешенная медиана y/p с весами p."""
    m = p > 0
    r, w = y[m] / p[m], p[m]
    order = np.argsort(r)
    cw = np.cumsum(w[order])
    k = r[order][np.searchsorted(cw, cw[-1] / 2)]
    return float(k), wape_score(y, k * p)


VARIANTS = {
    "база: профиль 2 нед (уровень и форма)": LevelShape(level_weeks=2, shape_weeks=2),
    "база: профиль 4 нед (уровень и форма)": LevelShape(level_weeks=4, shape_weeks=4),
    "уровень 1 нед, форма 8 нед": LevelShape(level_weeks=1, shape_weeks=8),
    "уровень 2 нед, форма 4 нед": LevelShape(level_weeks=2, shape_weeks=4),
    "уровень 2 нед, форма 8 нед": LevelShape(level_weeks=2, shape_weeks=8),
    "уровень 2 нед, форма 12 нед": LevelShape(level_weeks=2, shape_weeks=12),
    "уровень 3 нед, форма 8 нед": LevelShape(level_weeks=3, shape_weeks=8),
    "уровень 4 нед, форма 8 нед": LevelShape(level_weeks=4, shape_weeks=8),
    "уровень 2/8 + уровень будней по дням недели (3 нед)": LevelShape(level_weeks=3, shape_weeks=8, level_by_dow=True),
    "уровень 2/8 + очистка аномалий": LevelShape(level_weeks=2, shape_weeks=8, clean=True),
    "уровень 3/8 + очистка аномалий": LevelShape(level_weeks=3, shape_weeks=8, clean=True),
    "уровень 2/8 + среднее вместо медианы": LevelShape(level_weeks=2, shape_weeks=8, level_stat="mean"),
    "уровень 2/8 + тренд, затухание 0.8": LevelShape(level_weeks=2, shape_weeks=8, trend_damping=0.8),
    "уровень 2/8 + тренд, затухание 0.95": LevelShape(level_weeks=2, shape_weeks=8, trend_damping=0.95),
}


def main() -> None:
    pd.set_option("display.width", 250)
    full = load_frame()
    rows = []
    for fold in FOLDS:
        origin, end = pd.Timestamp(fold.origin), pd.Timestamp(fold.end)
        hist = full[full.date <= origin]
        grid = full[(full.date > origin) & (full.date <= end)].reset_index(drop=True)
        y = grid.boardings.to_numpy(dtype=float)
        for name, cfg in VARIANTS.items():
            p = forecast(hist, grid.drop(columns="boardings"), origin, cfg)
            k, s_k = best_scale(y, p)
            rows.append({"fold": fold.name, "model": name, "wape_score": wape_score(y, p),
                         "bias_pct": (p.sum() / y.sum() - 1) * 100, "best_k": k, "score_at_best_k": s_k})
    res = pd.DataFrame(rows)
    res.to_csv(TABLES / "exp2_level_shape.csv", index=False, float_format="%.4f")
    fold_names = [f.name for f in FOLDS]
    pv = res.pivot(index="model", columns="fold", values="wape_score")[fold_names].loc[list(VARIANTS)]
    pv["среднее"] = pv.mean(axis=1)
    pv["худший"] = pv[fold_names].min(axis=1)
    print(pv.round(4).to_string())
    kk = res.pivot(index="model", columns="fold", values="best_k")[fold_names].loc[list(VARIANTS)]
    print("\nоптимальный множитель уровня k по фолдам:\n", kk.round(3).to_string())
    sk = res.pivot(index="model", columns="fold", values="score_at_best_k")[fold_names].loc[list(VARIANTS)]
    print("\nскор при оптимальном k:\n", sk.round(4).to_string())
    pv.round(4).to_csv(TABLES / "exp2_level_shape_pivot.csv")


if __name__ == "__main__":
    main()
