"""Сводный бэктест: классические модели, foundation-модели и их ансамбли на одних фолдах.

Запуск: uv run python analysis/s11_ensembles.py (после s06 и s07)
"""

from functools import partial
from itertools import combinations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import DATA, SERIES, TABLES, TEXT_SECONDARY, savefig, wape_score
from models import ProfileConfig, profile_forecast
from s06_backtest import FOLDS, load_frame

FM_FILES = ["chronos2", "t0beta", "timesfm"]
# TiRex-2 считается в Docker (s13_tirex2_docker.py); подключаем, если его прогнозы уже есть
if (DATA / "fm_backtest_preds_tirex2.parquet").exists():
    FM_FILES.append("tirex2")
BASE_MEMBERS = {
    "профиль 4 нед": partial(profile_forecast, cfg=ProfileConfig(weeks=4)),
    "профиль 2 нед": partial(profile_forecast, cfg=ProfileConfig(weeks=2)),
}
FM_MEMBERS = ["Chronos-2 + календарь", "t0-beta + календарь", "TimesFM 3.0 + календарь"]
if "tirex2" in FM_FILES:
    FM_MEMBERS.append("TiRex-2 + календарь")


def collect() -> pd.DataFrame:
    full = load_frame()
    fm = pd.concat([pd.read_parquet(DATA / f"fm_backtest_preds_{f}.parquet") for f in FM_FILES])
    frames = []
    for fold in FOLDS:
        origin, end = pd.Timestamp(fold.origin), pd.Timestamp(fold.end)
        hist = full[full.date <= origin]
        grid = full[(full.date > origin) & (full.date <= end)].reset_index(drop=True)
        out = grid[["route", "ts", "boardings"]].copy()
        for name, fn in BASE_MEMBERS.items():
            out[name] = fn(hist, grid.drop(columns="boardings"), origin)
        f = fm[fm.fold == fold.name].pivot_table(index=["route", "ts"], columns="model", values="pred").reset_index()
        out = out.merge(f, on=["route", "ts"], how="left").fillna(0)
        # Выравнивание уровня: у FM берём только форму внутри недели, сумму маршрута за неделю - у профиля
        week = out.ts.dt.to_period("W")
        ref = out.groupby([out.route, week])["профиль 4 нед"].transform("sum")
        for m in FM_MEMBERS:
            tot = out.groupby([out.route, week])[m].transform("sum")
            out[m + " (уровень профиля)"] = np.where(tot > 0, out[m] * ref / tot.where(tot > 0, 1), 0)
        out["fold"] = fold.name
        frames.append(out)
    return pd.concat(frames, ignore_index=True)


def score_table(df: pd.DataFrame, members: list[str]) -> pd.DataFrame:
    rows = []
    candidates = {m: [m] for m in members}
    for k in (2, 3, 4):
        for combo in combinations(members, k):
            candidates[" + ".join(combo)] = list(combo)
    for name, cols in candidates.items():
        for fold, g in df.groupby("fold"):
            p = g[cols].mean(axis=1)
            rows.append({"model": name, "n": len(cols), "fold": fold, "wape_score": wape_score(g.boardings, p),
                         "median_ens": wape_score(g.boardings, g[cols].median(axis=1)) if len(cols) > 2 else np.nan})
    res = pd.DataFrame(rows)
    pv = res.pivot(index="model", columns="fold", values="wape_score")[[f.name for f in FOLDS]]
    pv["среднее"] = pv.mean(axis=1)
    pv["худший фолд"] = pv[[f.name for f in FOLDS]].min(axis=1)
    return pv.sort_values("среднее", ascending=False)


def plot_top(pv: pd.DataFrame, members: list[str], n: int = 14) -> None:
    top = pv.head(n)
    singles = pv[pv.index.isin(members)]
    show = pd.concat([top, singles[~singles.index.isin(top.index)]]).drop_duplicates()
    fig, ax = plt.subplots(figsize=(12, 0.42 * len(show) + 1.5))
    y = np.arange(len(show))
    for i, fold in enumerate([f.name for f in FOLDS]):
        ax.scatter(show[fold], y, color=SERIES[i], s=28, label=fold, zorder=3)
    ax.scatter(show["среднее"], y, color="#0b0b0b", marker="|", s=260, lw=2, label="среднее", zorder=4)
    ax.set_yticks(y, show.index, fontsize=8)
    ax.invert_yaxis()
    ax.axvline(0.88, color=TEXT_SECONDARY, lw=0.8)
    ax.set_xlabel("WAPE-score")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.06), ncols=5, fontsize=7)
    ax.set_title("Одиночные модели и ансамбли (среднее прогнозов): бэктест на 4 фолдах", loc="left")
    savefig(fig, "17_backtest_ensembles")


def main() -> None:
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 80)
    df = collect()
    members = list(BASE_MEMBERS) + FM_MEMBERS
    pv = score_table(df, members)
    aligned = ["профиль 4 нед", "профиль 2 нед"] + [m + " (уровень профиля)" for m in FM_MEMBERS]
    pva = score_table(df, aligned)
    print("FM с уровнем профиля:")
    print(pva.round(4).head(12).to_string())
    pva.round(4).to_csv(TABLES / "backtest_ensembles_level_aligned.csv")
    print(pv.round(4).head(25).to_string())
    pv.round(4).to_csv(TABLES / "backtest_ensembles.csv")
    no_nc = pv[~pv.index.str.contains("TimesFM")]
    print("\nбез некоммерческих весов (TimesFM):\n", no_nc.round(4).head(8).to_string())
    plot_top(pv, members)


if __name__ == "__main__":
    main()
