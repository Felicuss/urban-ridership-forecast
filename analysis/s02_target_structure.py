"""Структура целевой переменной по готовым labels: уровни, недельная и суточная
сезонность, праздники, помесячный уровень, аномальные дни.

Запуск: uv run python analysis/s02_target_structure.py
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from calendar_ru import calendar_frame
from common import (
    ACTIVE_ROUTES,
    MUTED,
    SERIES,
    TABLES,
    TEST_END,
    TEXT_SECONDARY,
    TRAIN_START,
    load_labels,
    savefig,
)

DOW_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTH_RU = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


def daily_frame(df: pd.DataFrame) -> pd.DataFrame:
    daily = df.groupby(["route", "date"], as_index=False)["boardings"].sum()
    cal = calendar_frame(TRAIN_START, TEST_END)
    return daily.merge(cal, on="date", how="left")


def plot_daily(daily: pd.DataFrame) -> None:
    fig, axes = plt.subplots(3, 3, figsize=(15, 9), sharex=True)
    holidays_ = daily.loc[daily["is_holiday"], "date"].drop_duplicates()
    for ax, route in zip(axes.flat, ACTIVE_ROUTES, strict=True):
        s = daily[daily.route == route].set_index("date")["boardings"] / 1000
        for d in holidays_:
            ax.axvspan(d, d + pd.Timedelta(days=1), color=SERIES[1], alpha=0.12, lw=0)
        ax.plot(s.index, s.values, color=MUTED, lw=0.7)
        ax.plot(s.index, s.rolling(7, center=True).mean(), color=SERIES[0], lw=1.8)
        ax.axvline(pd.Timestamp("2025-09-01"), color=TEXT_SECONDARY, lw=0.8)
        ax.set_title(f"Маршрут {route}", loc="left")
        ax.set_ylim(bottom=0)
        ax.set_ylabel("тыс. посадок/день")
    fig.suptitle(
        "Посадки по дням: серая линия - день, синяя - скользящее среднее 7 дней; "
        "оранжевые полосы - праздники, вертикаль - начало test (1 сен)",
        x=0.01, ha="left", fontsize=11,
    )
    fig.autofmt_xdate()
    fig.tight_layout()
    savefig(fig, "01_daily_by_route")


def hourly_profiles(df: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    x = df.merge(cal[["date", "day_type"]], on="date")
    x["kind"] = x["day_type"].replace({"holiday": "sunday"})
    prof = x.groupby(["route", "kind", "hour"])["boardings"].mean().unstack("hour")
    shares = prof.div(prof.sum(axis=1), axis=0)
    fig, axes = plt.subplots(3, 3, figsize=(14, 9), sharex=True, sharey=True)
    labels = {"workday": "рабочий", "saturday": "суббота", "sunday": "воскресенье и праздник"}
    for ax, route in zip(axes.flat, ACTIVE_ROUTES, strict=True):
        for i, (kind, lab) in enumerate(labels.items()):
            ax.plot(range(24), shares.loc[(route, kind)] * 100, color=SERIES[i], lw=1.8, label=lab)
        ax.set_title(f"Маршрут {route}", loc="left")
        ax.set_xticks(range(0, 24, 3))
        ax.set_ylabel("% суточных посадок")
    axes.flat[0].legend(loc="upper right")
    for ax in axes[-1]:
        ax.set_xlabel("час")
    fig.suptitle("Форма суток: доля посадок по часам по типу дня (январь-октябрь)", x=0.01, ha="left")
    fig.tight_layout()
    savefig(fig, "02_hourly_profile_by_daytype")
    return shares


def dow_index(daily: pd.DataFrame) -> pd.DataFrame:
    regular = daily[~daily["is_holiday"]]
    idx = regular.groupby(["route", "dow"])["boardings"].median().unstack("dow")
    base = idx[[1, 2, 3]].mean(axis=1)
    idx = idx.div(base, axis=0)
    fig, ax = plt.subplots(figsize=(8, 5))
    im = ax.imshow(idx.values, cmap="Blues", vmin=0.3, vmax=1.1, aspect="auto")
    for i in range(idx.shape[0]):
        for j in range(idx.shape[1]):
            v = idx.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8,
                    color="white" if v > 0.8 else "black")
    ax.set_xticks(range(7), DOW_RU)
    ax.set_yticks(range(len(idx)), [f"м. {r}" for r in idx.index])
    ax.grid(False)
    ax.set_title("Медиана посадок в день недели к среднему Вт-Чт (без праздников)", loc="left")
    fig.colorbar(im, ax=ax, shrink=0.8)
    savefig(fig, "03_dow_index")
    return idx


def monthly_index(daily: pd.DataFrame) -> pd.DataFrame:
    work = daily[daily["day_type"] == "workday"].copy()
    work["month"] = work["date"].dt.month
    lvl = work.groupby(["route", "month"])["boardings"].median().unstack("month")
    idx = lvl.div(lvl[[9, 10]].mean(axis=1), axis=0)
    fig, ax = plt.subplots(figsize=(10, 5))
    im = ax.imshow(idx.values, cmap="RdBu", vmin=0.5, vmax=1.5, aspect="auto")
    for i in range(idx.shape[0]):
        for j in range(idx.shape[1]):
            v = idx.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8,
                    color="white" if abs(v - 1) > 0.3 else "black")
    ax.set_xticks(range(idx.shape[1]), [MONTH_RU[m - 1] for m in idx.columns])
    ax.set_yticks(range(len(idx)), [f"м. {r}" for r in idx.index])
    ax.grid(False)
    ax.set_title(
        "Медиана посадок в рабочий день по месяцам, индекс к среднему сен-окт (=1.00)", loc="left"
    )
    fig.colorbar(im, ax=ax, shrink=0.8)
    savefig(fig, "04_monthly_index_workdays")
    return lvl


def holiday_effect(daily: pd.DataFrame) -> pd.DataFrame:
    """Праздничный день против медианы обычных воскресений и рабочих дней в окне ±28 дней."""
    rows = []
    hol_days = daily.loc[daily["is_holiday"], "date"].drop_duplicates().sort_values()
    for d in hol_days:
        win = daily[(daily.date >= d - pd.Timedelta(days=28)) & (daily.date <= d + pd.Timedelta(days=28))]
        win = win[~win["is_holiday"]]
        sun = win[win.day_type == "sunday"].groupby("route")["boardings"].median()
        wd = win[win.day_type == "workday"].groupby("route")["boardings"].median()
        day = daily[daily.date == d].set_index("route")["boardings"]
        tot = day[ACTIVE_ROUTES].sum()
        rows.append(
            {
                "date": d.date(),
                "dow": DOW_RU[d.dayofweek],
                "name": daily.loc[daily.date == d, "holiday_name"].iloc[0],
                "to_sunday": tot / sun[ACTIVE_ROUTES].sum(),
                "to_workday": tot / wd[ACTIVE_ROUTES].sum(),
            }
        )
    eff = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(12, 4.5))
    x = np.arange(len(eff))
    ax.bar(x, eff["to_sunday"], width=0.7, color=SERIES[0])
    ax.axhline(1.0, color=TEXT_SECONDARY, lw=0.8)
    ax.set_xticks(x, [f"{r.date:%d.%m}\n{r.dow}" for r in eff.itertuples()], fontsize=7)
    ax.set_ylabel("посадки / медиана воскресенья")
    ax.set_title(
        "Праздничные дни 2025: суммарные посадки относительно обычного воскресенья рядом (±4 недели)",
        loc="left",
    )
    savefig(fig, "05_holiday_vs_sunday")
    eff.to_csv(TABLES / "holiday_effect.csv", index=False, float_format="%.3f")
    return eff


def anomalies(daily: pd.DataFrame) -> pd.DataFrame:
    """Дни, где маршрут отклоняется от медианы того же типа дня в окне ±21 день больше чем на 35 %."""
    d = daily[daily.route.isin(ACTIVE_ROUTES)].copy()
    d["kind"] = d["day_type"].replace({"holiday": "sunday"})
    out = []
    for _, g in d.groupby(["route", "kind"]):
        g = g.sort_values("date").set_index("date")
        exp = g["boardings"].rolling("43D", center=True, min_periods=3).median()
        g = g.assign(expected=exp, ratio=g["boardings"] / exp)
        out.append(g.reset_index())
    res = pd.concat(out)
    flagged = res[(res.ratio < 0.65) | (res.ratio > 1.35)]
    flagged = flagged[["route", "date", "day_type", "boardings", "expected", "ratio"]].sort_values(
        ["route", "date"]
    )
    flagged.to_csv(TABLES / "anomalous_days.csv", index=False, float_format="%.2f")
    return flagged


def hour_mass(df: pd.DataFrame) -> pd.Series:
    """Какая доля суммарных посадок (знаменатель WAPE) приходится на каждый час."""
    return df.groupby("hour")["boardings"].sum() / df["boardings"].sum()


def main() -> None:
    df = load_labels()
    df = df[df.route.isin(ACTIVE_ROUTES)]
    cal = calendar_frame(TRAIN_START, TEST_END)
    daily = daily_frame(df)

    plot_daily(daily)
    shares = hourly_profiles(df, cal)
    dow = dow_index(daily)
    lvl = monthly_index(daily)
    eff = holiday_effect(daily)
    anom = anomalies(daily)
    mass = hour_mass(df)

    pd.set_option("display.width", 200)
    print("DOW index:\n", dow.round(2))
    print("Monthly workday median:\n", lvl.round(0))
    print("Holiday effect:\n", eff.round(2).to_string())
    print(f"Anomalous route-days: {len(anom)}")
    print(anom.to_string())
    print("Hour mass %:\n", (mass * 100).round(1).to_string())
    peak = shares.xs("workday", level="kind")
    print("Workday peak hour per route:", peak.idxmax(axis=1).to_dict())
    (mass * 100).round(2).rename("share_pct").to_csv(TABLES / "hour_mass.csv")
    lvl.round(0).to_csv(TABLES / "monthly_workday_median.csv")
    dow.round(3).to_csv(TABLES / "dow_index.csv")


if __name__ == "__main__":
    main()
