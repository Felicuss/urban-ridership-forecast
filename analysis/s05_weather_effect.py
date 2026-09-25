"""Есть ли у погоды эффект после удаления календаря и локального уровня.

Остаток дня = log(посадки / ожидание), ожидание - медиана того же маршрута и типа дня
в окне ±21 день без самого дня. Дни перекрытий (|остаток| > 0.35) выбрасываем:
их объясняет выпуск вагонов, а не погода. Остатки усредняем по маршрутам (медиана)
и регрессируем на погоду с HAC-ошибками.
Запуск: uv run python analysis/s05_weather_effect.py
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from calendar_ru import calendar_frame
from common import ACTIVE_ROUTES, ROOT, SERIES, TABLES, TEST_END, TEXT_SECONDARY, TRAIN_START, load_labels, savefig

WEATHER = ROOT / "external" / "weather_moscow_2025_hourly.csv"
DAY_HOURS = range(6, 23)


def daily_weather() -> pd.DataFrame:
    w = pd.read_csv(WEATHER, parse_dates=["ts"])
    w["date"] = w["ts"].dt.normalize()
    day = w[w["ts"].dt.hour.isin(DAY_HOURS)].groupby("date").agg(
        temp=("temperature_2m", "mean"),
        precip=("precipitation", "sum"),
        rain=("rain", "sum"),
        snow=("snowfall", "sum"),
        wind=("wind_speed_10m", "mean"),
    )
    day["temp_anom"] = day["temp"] - day["temp"].rolling(31, center=True, min_periods=10).mean()
    return day.reset_index()


def daily_residuals() -> pd.DataFrame:
    df = load_labels()
    df = df[df.route.isin(ACTIVE_ROUTES)]
    daily = df.groupby(["route", "date"], as_index=False)["boardings"].sum()
    cal = calendar_frame(TRAIN_START, TEST_END)
    daily = daily.merge(cal[["date", "day_type", "is_holiday"]], on="date")
    daily = daily[~daily.is_holiday & (daily.date >= "2025-01-13")]
    out = []
    for (_, _), g in daily.groupby(["route", "day_type"]):
        g = g.sort_values("date").set_index("date")
        s = g["boardings"].astype(float)
        # медиана окна без центрального дня
        exp = s.rolling("43D", center=True, min_periods=4).apply(
            lambda x: np.median(np.delete(x, len(x) // 2)) if len(x) > 2 else np.nan, raw=True
        )
        g = g.assign(resid=np.log(s / exp))
        out.append(g.reset_index())
    res = pd.concat(out)
    res = res[res.resid.abs() < 0.35]
    agg = res.groupby("date").agg(resid=("resid", "median"), day_type=("day_type", "first")).reset_index()
    return agg


def hourly_effect() -> pd.DataFrame:
    """Час с осадками против того же часа того же маршрута и типа дня в соседние недели."""
    df = load_labels()
    df = df[df.route.isin(ACTIVE_ROUTES) & df.hour.isin(DAY_HOURS)]
    cal = calendar_frame(TRAIN_START, TEST_END)
    df = df.merge(cal[["date", "day_type", "is_holiday"]], on="date")
    df = df[~df.is_holiday & (df.date >= "2025-01-13")]
    df = df.sort_values("date")
    grp = df.groupby(["route", "day_type", "hour"])["boardings"]
    df["exp"] = grp.transform(lambda s: s.rolling(7, center=True, min_periods=4).median())
    df = df[df.exp > 50]
    df["resid"] = np.log((df.boardings + 1) / (df.exp + 1))
    df = df[df.resid.abs() < 0.5]
    w = pd.read_csv(WEATHER, parse_dates=["ts"])[["ts", "precipitation", "rain", "snowfall", "temperature_2m"]]
    df = df.merge(w, on="ts", how="left")
    df["precip_bin"] = pd.cut(df["precipitation"], [-0.01, 0.0, 0.5, 2.0, 100], labels=["0", "0-0.5", "0.5-2", ">2"])
    tab = df.groupby("precip_bin", observed=True)["resid"].agg(["mean", "median", "count"])
    tab["effect_pct"] = (np.exp(tab["mean"]) - 1) * 100
    return tab


def main() -> None:
    pd.set_option("display.width", 200)
    wd = daily_weather()
    res = daily_residuals().merge(wd, on="date")
    res["is_work"] = (res.day_type == "workday").astype(int)
    res["heavy_precip"] = (res.precip >= 10).astype(int)
    res["frost"] = np.clip(-10 - res.temp, 0, None)  # градусы ниже -10
    model = smf.ols("resid ~ precip + snow + temp_anom + frost + is_work", data=res).fit(
        cov_type="HAC", cov_kwds={"maxlags": 7}
    )
    print(model.summary().tables[1])
    coefs = model.params.to_frame("coef").join(model.pvalues.rename("p_value"))
    coefs["effect_pct_per_unit"] = (np.exp(coefs["coef"]) - 1) * 100
    coefs.round(4).to_csv(TABLES / "weather_daily_ols.csv")

    by_dt = {}
    for dt_, g in res.groupby("day_type"):
        m = smf.ols("resid ~ precip + snow + temp_anom", data=g).fit(cov_type="HAC", cov_kwds={"maxlags": 7})
        by_dt[dt_] = (np.exp(m.params) - 1) * 100
        by_dt[dt_ + "_p"] = m.pvalues
    print("effect % per unit by day type:\n", pd.DataFrame(by_dt).round(3))

    hourly = hourly_effect()
    print("hourly precipitation bins:\n", hourly.round(4))
    hourly.round(4).to_csv(TABLES / "weather_hourly_precip_bins.csv")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    ax = axes[0]
    bin_labels = ["0", "0.1-2", "2-5", "5-10", "10-20", ">20"]
    bins = pd.cut(res.precip, [-0.1, 0.1, 2, 5, 10, 20, 60], labels=bin_labels)
    g = res.groupby(bins, observed=True)["resid"].agg(["mean", "sem", "count"])
    x = np.arange(len(g))
    ax.bar(x, (np.exp(g["mean"]) - 1) * 100, width=0.7, color=SERIES[0])
    ax.errorbar(x, (np.exp(g["mean"]) - 1) * 100, yerr=g["sem"] * 196, fmt="none", ecolor=TEXT_SECONDARY, lw=1)
    ax.set_xticks(x, [f"{lab}\nn={n}" for lab, n in g["count"].items()], fontsize=8)
    ax.axhline(0, color=TEXT_SECONDARY, lw=0.8)
    ax.set_xlabel("осадки за 06-22 ч, мм")
    ax.set_ylabel("отклонение посадок от ожидания, %")
    ax.set_title("Дневные осадки и отклонение посадок (±95 % ДИ)", loc="left")

    ax = axes[1]
    ax.bar(np.arange(len(hourly)), hourly["effect_pct"], width=0.7, color=SERIES[0])
    ax.set_xticks(np.arange(len(hourly)), [f"{b}\nn={c}" for b, c in hourly["count"].items()], fontsize=8)
    ax.axhline(0, color=TEXT_SECONDARY, lw=0.8)
    ax.set_xlabel("осадки в этот час, мм")
    ax.set_ylabel("отклонение посадок часа, %")
    ax.set_title("Почасовые осадки и отклонение посадок в тот же час", loc="left")
    fig.tight_layout()
    savefig(fig, "09_weather_precip_effect")

    res.to_csv(TABLES / "daily_residuals_weather.csv", index=False, float_format="%.4f")


if __name__ == "__main__":
    main()
