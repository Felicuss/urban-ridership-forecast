"""Зависимости, которые определяют, переносится ли октябрь на ноябрь-декабрь.

1. Дрейф формы суток по месяцам и связь вечерней доли с закатом.
2. Общий для сети фактор дневных отклонений (PCA остатков по маршрутам).
3. Эффект осадков по часам суток (пик против межпика).
Запуск: uv run python analysis/s15_dependencies.py (после s05 и s08)
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from calendar_ru import calendar_frame
from common import (
    ACTIVE_ROUTES, ROOT, SERIES, TABLES, TEST_END, TEXT_SECONDARY, TRAIN_START, load_labels, savefig,
)

MONTH_RU = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт"]
BANDS = {
    "утро 6-9": range(6, 10),
    "день 10-15": range(10, 16),
    "вечер 16-19": range(16, 20),
    "поздно 20-23": range(20, 24),
}


def workday_hours() -> pd.DataFrame:
    df = load_labels()
    df = df[df.route.isin(ACTIVE_ROUTES)]
    cal = calendar_frame(TRAIN_START, TEST_END)
    df = df.merge(cal[["date", "day_type"]], on="date")
    return df[df.day_type == "workday"]


def shape_drift(df: pd.DataFrame) -> pd.DataFrame:
    """Доли суточных посадок в будни по часовым полосам и месяцам (все 9 маршрутов) + время заката."""
    df = df.assign(month=df.date.dt.month)
    band = pd.Series(index=range(24), dtype=object)
    for name, hours in BANDS.items():
        band[list(hours)] = name
    df["band"] = df.hour.map(band).fillna("ночь 0-5")
    share = df.groupby(["month", "band"])["boardings"].sum().unstack()
    share = share.div(share.sum(axis=1), axis=0) * 100
    sun = pd.read_csv(ROOT / "external" / "daylight_moscow_2025.csv", parse_dates=["date", "sunset"])
    sun["month"] = sun.date.dt.month
    sunset = sun.groupby("month").sunset.apply(lambda s: (s.dt.hour + s.dt.minute / 60).mean())
    share["закат, ч"] = sunset.reindex(share.index)

    # L1-расстояние формы суток маршрута в месяце m до формы октября (доля «перераспределённых» посадок)
    per = df.groupby(["route", "month", "hour"])["boardings"].sum()
    per = per / per.groupby(level=[0, 1]).transform("sum")
    dist = {}
    for m in range(1, 11):
        d = (per.xs(m, level=1) - per.xs(10, level=1)).abs().groupby(level=0).sum() / 2 * 100
        dist[m] = d.mean()
    share["расстояние формы до октября, %"] = pd.Series(dist)
    return share


def plot_shape_drift(share: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.6))
    ax = axes[0]
    for i, band in enumerate(BANDS):
        ax.plot(share.index, share[band], color=SERIES[i], lw=2, marker="o", ms=4, label=band)
    ax.set_xticks(share.index, MONTH_RU)
    ax.set_ylabel("% суточных посадок в будни")
    ax.legend(ncols=2, loc="center left")
    ax.set_title("Доля часовых полос в будни по месяцам (9 маршрутов)", loc="left")
    ax = axes[1]
    ax.scatter(share["закат, ч"], share["поздно 20-23"], color=SERIES[0], s=40, zorder=3)
    for m, row in share.iterrows():
        ax.annotate(MONTH_RU[m - 1], (row["закат, ч"], row["поздно 20-23"]), xytext=(4, 3),
                    textcoords="offset points", fontsize=8, color=TEXT_SECONDARY)
    ax.set_xlabel("средний закат в месяце, ч")
    ax.set_ylabel("% посадок в 20-23 ч")
    ax.set_title("Поздний вечер против времени заката", loc="left")
    fig.tight_layout()
    savefig(fig, "19_shape_drift_daylight")


def common_factor() -> dict:
    """PCA остатков дня по маршрутам: какая доля дневных отклонений общая для всей сети."""
    res = pd.read_csv(TABLES / "daily_residuals_weather.csv", parse_dates=["date"])
    # s05 сохраняет медиану по маршрутам; для PCA нужны остатки маршрутов, пересчитаем их здесь
    df = load_labels()
    df = df[df.route.isin(ACTIVE_ROUTES)]
    daily = df.groupby(["route", "date"])["boardings"].sum().unstack(0)
    cal = calendar_frame(TRAIN_START, TEST_END).set_index("date")
    daily = daily[(~cal.is_holiday.reindex(daily.index)) & (daily.index >= "2025-01-13")]
    kind = cal.day_type.reindex(daily.index)
    resid = []
    for k in ("workday", "saturday", "sunday"):
        d = daily[kind == k]
        exp = d.rolling("43D", center=True, min_periods=4).median()
        resid.append(np.log(d / exp))
    r = pd.concat(resid).sort_index()
    r = r.where(r.abs() < 0.35).dropna()  # без дней перекрытий
    r = r - r.mean()
    cov = np.cov(r.T.values)
    eig = np.sort(np.linalg.eigvalsh(cov))[::-1]
    pc1 = eig[0] / eig.sum()
    corr = r.corr().values
    mean_corr = corr[np.triu_indices_from(corr, 1)].mean()
    # насколько общий фактор (среднее по маршрутам) объясняется погодой из s05
    common = r.mean(axis=1).rename("common")
    merged = res.set_index("date")[["precip", "snow", "temp_anom"]].join(common, how="inner")
    x = merged[["precip", "snow", "temp_anom"]].to_numpy()
    x = np.column_stack([np.ones(len(x)), x])
    beta, *_ = np.linalg.lstsq(x, merged.common.to_numpy(), rcond=None)
    fitted = x @ beta
    r2 = 1 - ((merged.common - fitted) ** 2).sum() / ((merged.common - merged.common.mean()) ** 2).sum()
    return {"days": len(r), "pc1_share": pc1, "mean_pairwise_corr": mean_corr, "weather_r2_of_common": r2}


def rain_by_hour(df: pd.DataFrame) -> pd.DataFrame:
    """Эффект часа с осадками ≥0.5 мм на посадки этого часа, отдельно по часовым полосам."""
    w = pd.read_csv(ROOT / "external" / "weather_moscow_2025_hourly.csv", parse_dates=["ts"])
    df = df[df.date >= "2025-01-13"].sort_values("date")
    grp = df.groupby(["route", "hour"])["boardings"]
    df = df.assign(exp=grp.transform(lambda s: s.rolling(9, center=True, min_periods=5).median()))
    df = df[df.exp > 50].merge(w[["ts", "precipitation"]], on="ts")
    df["resid"] = np.log((df.boardings + 1) / (df.exp + 1))
    df = df[df.resid.abs() < 0.5]
    df["wet"] = df.precipitation >= 0.5
    band = {h: name for name, hours in BANDS.items() for h in hours}
    df["band"] = df.hour.map(band)
    out = df.dropna(subset=["band"]).groupby(["band", "wet"])["resid"].mean().unstack()
    out["эффект, %"] = (np.exp(out[True] - out[False]) - 1) * 100
    out["часов с осадками"] = df.dropna(subset=["band"]).groupby("band")["wet"].sum()
    return out


def main() -> None:
    pd.set_option("display.width", 200)
    df = workday_hours()
    share = shape_drift(df)
    print(share.round(2).to_string())
    share.round(3).to_csv(TABLES / "shape_drift_by_month.csv")
    plot_shape_drift(share)
    cf = common_factor()
    print("\nобщий фактор дневных отклонений:", {k: round(v, 3) for k, v in cf.items()})
    pd.Series(cf).round(4).to_csv(TABLES / "daily_residual_common_factor.csv")
    rb = rain_by_hour(df)
    print("\nосадки по часовым полосам (будни):\n", rb.round(3).to_string())
    rb.round(4).to_csv(TABLES / "rain_effect_by_hour_band.csv")


if __name__ == "__main__":
    main()
