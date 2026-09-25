"""Бэктест моделей на нескольких фолдах (origin -> горизонт 1-2 месяца), метрика WAPE-score.

Запуск: uv run python analysis/s06_backtest.py
"""

from dataclasses import dataclass
from functools import partial

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import SERIES, TABLES, TEST_END, TEXT_SECONDARY, TRAIN_START, load_labels, savefig, wape_score
from models import (
    LgbConfig,
    ProfileConfig,
    add_calendar,
    add_weather,
    baseline_blocks,
    ensemble,
    lgb_forecast,
    lgb_ratio_forecast,
    profile_forecast,
    seasonal_naive,
)


@dataclass(frozen=True)
class Fold:
    name: str
    origin: str
    end: str


FOLDS = [
    Fold("C: до 30.04 -> май-июнь", "2025-04-30", "2025-06-30"),
    Fold("E: до 30.06 -> июль-август", "2025-06-30", "2025-08-31"),
    Fold("A: до 31.08 -> сентябрь-октябрь", "2025-08-31", "2025-10-31"),
    Fold("B: до 30.09 -> октябрь", "2025-09-30", "2025-10-31"),
]

MODELS = {
    "baseline организаторов (3 блока)": baseline_blocks,
    "seasonal naive (последняя неделя)": seasonal_naive,
    "профиль 2 нед, медиана": partial(profile_forecast, cfg=ProfileConfig(weeks=2)),
    "профиль 4 нед, медиана": partial(profile_forecast, cfg=ProfileConfig(weeks=4)),
    "профиль 6 нед, медиана": partial(profile_forecast, cfg=ProfileConfig(weeks=6)),
    "профиль 8 нед, медиана": partial(profile_forecast, cfg=ProfileConfig(weeks=8)),
    "профиль 4 нед, среднее": partial(profile_forecast, cfg=ProfileConfig(weeks=4, stat="mean")),
    "профиль 4 нед, по дням Пн-Пт": partial(profile_forecast, cfg=ProfileConfig(weeks=4, by_dow=True)),
    "профиль 4 нед без правил праздников": partial(profile_forecast, cfg=ProfileConfig(weeks=4, holiday_rules=False)),
    "профиль 4 нед без календаря": partial(profile_forecast, cfg=ProfileConfig(weeks=4, calendar=False)),
    "профиль 4 нед + погода": partial(profile_forecast, cfg=ProfileConfig(weeks=4, weather=True)),
    "LightGBM L1 без погоды": partial(lgb_forecast, cfg=LgbConfig(use_weather=False)),
    "LightGBM L1 + погода": partial(lgb_forecast, cfg=LgbConfig(use_weather=True)),
    "LightGBM-поправка к профилю без погоды": partial(
        lgb_ratio_forecast, cfg=LgbConfig(use_weather=False, num_boost_round=300)),
    "LightGBM-поправка к профилю + погода": partial(
        lgb_ratio_forecast, cfg=LgbConfig(use_weather=True, num_boost_round=300)),
    "ансамбль: профили 2 и 4 нед + naive": ensemble(
        partial(profile_forecast, cfg=ProfileConfig(weeks=2)),
        partial(profile_forecast, cfg=ProfileConfig(weeks=4)),
        seasonal_naive,
    ),
}

# Модели, для которых раскладываем ошибку на уровень и форму.
DECOMPOSE = [
    "профиль 4 нед, медиана",
    "профиль 4 нед + погода",
    "профиль 4 нед без календаря",
    "LightGBM-поправка к профилю + погода",
    "ансамбль: профили 2 и 4 нед + naive",
]


def load_frame() -> pd.DataFrame:
    df = load_labels()
    df = add_calendar(df, TRAIN_START, TEST_END)
    df = add_weather(df)
    return df.sort_values(["route", "date", "hour"]).reset_index(drop=True)


def run() -> tuple[pd.DataFrame, dict]:
    full = load_frame()
    scores, preds = [], {}
    for fold in FOLDS:
        origin = pd.Timestamp(fold.origin)
        history = full[full.date <= origin]
        grid = full[(full.date > origin) & (full.date <= pd.Timestamp(fold.end))].reset_index(drop=True)
        y = grid["boardings"].to_numpy()
        for name, fn in MODELS.items():
            p = fn(history, grid.drop(columns="boardings"), origin)
            preds[(fold.name, name)] = p
            scores.append({"fold": fold.name, "model": name, "wape_score": wape_score(y, p),
                           "bias_pct": (p.sum() / y.sum() - 1) * 100})
            print(f"{fold.name:34s} {name:40s} {scores[-1]['wape_score']:.4f} bias {scores[-1]['bias_pct']:+.1f}%")
    return pd.DataFrame(scores), {"full": full, "preds": preds}


def oracle_scores(full: pd.DataFrame, preds: dict) -> pd.DataFrame:
    """Сколько ошибки даёт уровень, а сколько форма: масштабируем прогноз под фактическую сумму
    (1) по маршруту за весь горизонт, (2) по маршруту за каждый день."""
    rows = []
    for fold in FOLDS:
        origin = pd.Timestamp(fold.origin)
        g = full[(full.date > origin) & (full.date <= pd.Timestamp(fold.end))].reset_index(drop=True)
        for name in DECOMPOSE:
            p = pd.Series(preds[(fold.name, name)])
            y = g.boardings
            res = {"fold": fold.name, "model": name, "raw": wape_score(y, p)}
            for label, keys in (("oracle_route_level", ["route"]), ("oracle_route_day", ["route", "date"])):
                ys = y.groupby([g[k] for k in keys]).transform("sum")
                ps = p.groupby([g[k] for k in keys]).transform("sum")
                scaled = np.where(ps > 0, p * ys / ps.where(ps > 0, 1), 0)
                res[label] = wape_score(y, scaled)
            rows.append(res)
    return pd.DataFrame(rows)


def baseline_calibration(full: pd.DataFrame) -> pd.DataFrame:
    """Baseline организаторов (среднее Jan-Oct) по месяцам: какой скор он дал бы на каждом месяце."""
    p = baseline_blocks(full, full, pd.Timestamp(TEST_END))
    full = full.assign(pred=p, month=full.date.dt.month)
    return full.groupby("month").apply(lambda g: wape_score(g.boardings, g.pred), include_groups=False).rename(
        "baseline_score"
    )


def error_breakdown(full: pd.DataFrame, pred: np.ndarray, fold: Fold) -> dict:
    origin = pd.Timestamp(fold.origin)
    g = full[(full.date > origin) & (full.date <= pd.Timestamp(fold.end))].reset_index(drop=True)
    g = g.assign(pred=pred, abs_err=np.abs(g.boardings - pred))
    total = g.boardings.sum()
    by_route = g.groupby("route").agg(abs_err=("abs_err", "sum"), y=("boardings", "sum"))
    by_route["share_of_wape_pct"] = by_route.abs_err / total * 100
    by_route["route_wape"] = by_route.abs_err / by_route.y
    by_kind = g.groupby("kind").agg(abs_err=("abs_err", "sum"), y=("boardings", "sum"))
    by_kind["share_of_wape_pct"] = by_kind.abs_err / total * 100
    by_hour = g.groupby("hour")["abs_err"].sum() / total * 100
    return {"route": by_route, "kind": by_kind, "hour": by_hour, "frame": g}


def plot_scores(scores: pd.DataFrame) -> None:
    pv = scores.pivot(index="model", columns="fold", values="wape_score")[[f.name for f in FOLDS]]
    pv = pv.loc[list(MODELS)]
    fig, ax = plt.subplots(figsize=(11, 6.5))
    y = np.arange(len(pv))
    for i, fold in enumerate(pv.columns):
        ax.scatter(pv[fold], y, color=SERIES[i], s=40, label=fold, zorder=3)
    ax.set_yticks(y, pv.index)
    ax.invert_yaxis()
    ax.set_xlabel("WAPE-score (больше - лучше)")
    ax.axvline(0.88, color=TEXT_SECONDARY, lw=0.8)
    ax.text(0.881, len(pv) - 0.6, "0.88: максимум баллов", fontsize=8, color=TEXT_SECONDARY)
    ax.legend(loc="lower left", ncols=2)
    ax.set_title("Бэктест: WAPE-score моделей по фолдам", loc="left")
    savefig(fig, "10_backtest_scores")


def plot_example(bd: dict, fold: Fold, routes=(17, 50)) -> None:
    g = bd["frame"]
    start = pd.Timestamp(fold.origin) + pd.Timedelta(days=1)
    g = g[(g.date >= start) & (g.date < start + pd.Timedelta(days=14))]
    fig, axes = plt.subplots(len(routes), 1, figsize=(14, 3.2 * len(routes)), sharex=True)
    for ax, route in zip(axes, routes, strict=True):
        x = g[g.route == route]
        ax.plot(x.ts, x.boardings, color=SERIES[0], lw=1.4, label="факт")
        ax.plot(x.ts, x.pred, color=SERIES[1], lw=1.4, label="прогноз")
        ax.set_title(f"Маршрут {route}", loc="left")
        ax.set_ylabel("посадок в час")
    axes[0].legend(loc="upper right")
    fig.suptitle(f"Фолд {fold.name}: первые две недели горизонта, лучшая модель", x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    savefig(fig, "11_backtest_example")


def main() -> None:
    pd.set_option("display.width", 220)
    scores, ctx = run()
    scores.to_csv(TABLES / "backtest_scores.csv", index=False, float_format="%.4f")
    pv = scores.pivot(index="model", columns="fold", values="wape_score").loc[list(MODELS)]
    pv["среднее"] = pv.mean(axis=1)
    print(pv.round(4).to_string())
    pv.round(4).to_csv(TABLES / "backtest_scores_pivot.csv")
    plot_scores(scores)

    orc = oracle_scores(ctx["full"], ctx["preds"])
    print(orc.round(4).to_string())
    orc.round(4).to_csv(TABLES / "backtest_oracle_decomposition.csv", index=False)

    calib = baseline_calibration(ctx["full"])
    print("baseline organizers by month:\n", calib.round(3))
    calib.round(4).to_csv(TABLES / "baseline_score_by_month.csv")

    best = pv["среднее"].idxmax()
    fold_b = FOLDS[3]
    bd = error_breakdown(ctx["full"], ctx["preds"][(fold_b.name, best)], fold_b)
    print("best model:", best)
    print(bd["route"].round(3).to_string())
    print(bd["kind"].round(3).to_string())
    print((bd["hour"]).round(2).to_string())
    bd["route"].round(4).to_csv(TABLES / "best_error_by_route_foldB.csv")
    plot_example(bd, fold_b)


if __name__ == "__main__":
    main()
