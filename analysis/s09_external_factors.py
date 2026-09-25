"""Внешние факторы: сезонный уровень ноября-декабря по городской статистике, проверка переноса
на наши маршруты, сводная регрессия эффектов календаря, каникул и погоды.

Запуск: uv run python analysis/s09_external_factors.py (после s05 и s08)
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from common import ACTIVE_ROUTES, ROOT, SERIES, TABLES, TEXT_SECONDARY, load_labels, savefig

EXT = ROOT / "external"
MONTH_RU = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
# Чистый прирост сети от Т1 (запущен 12.11.2025, около 77 тыс. поездок в будни по sobyanin.ru).
# Т1 заменил маршрут 90 и частично забрал пассажиров других маршрутов, поэтому чистый прирост
# берём 40 тыс. в будни (середина оценки 30-50 тыс.), в выходные 0.6 от будня.
T1_START = pd.Timestamp("2025-11-12")
T1_NET_WORKDAY = 40_000


def day_weights() -> dict:
    """Вес типа дня относительно рабочего по нашим 9 маршрутам (медианы по неделям без перекрытий)."""
    df = load_labels()
    df = df[df.route.isin(ACTIVE_ROUTES)]
    cal = calendar_table()
    d = df.groupby("date", as_index=False)["boardings"].sum().merge(cal, on="date")
    d = d[(d.date >= "2025-02-01") & (d.date <= "2025-06-01") & ~d.date.between("2025-03-31", "2025-04-30")]
    wd = d[d.kind == "workday"]["boardings"].median()
    return {k: d[d.kind == k]["boardings"].median() / wd for k in ("workday", "saturday", "sunday", "holiday")}


def calendar_table() -> pd.DataFrame:
    parts = []
    for y in (2019, 2022, 2023, 2024, 2025):
        c = pd.read_csv(EXT / f"production_calendar_{y}_isdayoff.csv", parse_dates=["date"])
        parts.append(c)
    cal = pd.concat(parts)
    dow = cal.date.dt.dayofweek
    off = cal.isdayoff_code.isin([1, 8])
    cal["kind"] = np.select(
        [~off, off & (dow == 5), off & (dow == 6), off & (dow < 5)],
        ["workday", "saturday", "sunday", "holiday"],
        default="workday",
    )
    return cal


def seasonal_ratios(weights: dict) -> pd.DataFrame:
    """Ноя/Окт и Дек/Окт в пересчёте на «эквивалент рабочего дня» по календарю каждого года."""
    m = pd.read_csv(EXT / "datamos_62521_monthly_ridership.csv")
    cal = calendar_table()
    cal["w"] = cal.kind.map(weights)
    cal["year"], cal["month"] = cal.date.dt.year, cal.date.dt.month
    w = cal.groupby(["year", "month"])["w"].sum().rename("w_days").reset_index()
    t1 = cal[cal.date >= T1_START].assign(t1=lambda x: x.w * T1_NET_WORKDAY).groupby(["year", "month"])["t1"].sum()
    rows = []
    for tt in ("Трамвай", "Автобус", "Московский метрополитен"):
        x = m[m.transport == tt].merge(w, on=["year", "month"])
        for y, g in x.groupby("year"):
            g = g.set_index("month")
            if not {10, 11, 12}.issubset(g.index):
                continue
            eq = g.passengers / g.w_days
            row = {"transport": tt, "year": y, "nov_oct_raw_per_day": g.per_day[11] / g.per_day[10],
                   "dec_oct_raw_per_day": g.per_day[12] / g.per_day[10],
                   "nov_oct_calendar_adj": eq[11] / eq[10], "dec_oct_calendar_adj": eq[12] / eq[10]}
            if tt == "Трамвай" and y == 2025:
                p = g.passengers.astype(float)
                for mm in (11, 12):
                    p[mm] -= t1.get((2025, mm), 0)
                eq2 = p / g.w_days
                row["nov_oct_adj_minus_T1"] = eq2[11] / eq2[10]
                row["dec_oct_adj_minus_T1"] = eq2[12] / eq2[10]
            rows.append(row)
    return pd.DataFrame(rows)


def routes_vs_city(weights: dict) -> tuple[pd.DataFrame, float, float]:
    """Помесячный индекс наших 9 маршрутов против городского трамвая, оба с поправкой на календарь."""
    df = load_labels()
    df = df[df.route.isin(ACTIVE_ROUTES)]
    ours = df.groupby(df.date.dt.month)["boardings"].sum()
    m = pd.read_csv(EXT / "datamos_62521_monthly_ridership.csv")
    city = m[(m.transport == "Трамвай") & (m.year == 2025)].set_index("month")["passengers"]
    cal = calendar_table()
    cal = cal[cal.date.dt.year == 2025]
    w = cal.assign(w=cal.kind.map(weights)).groupby(cal.date.dt.month)["w"].sum()
    idx = pd.DataFrame({"ours": ours / w.loc[ours.index], "city": city / w})
    idx = idx / idx.loc[10]
    both = idx.dropna()
    both = both[both.index != 1]  # январь: неполная неделя праздников искажает оба ряда по-разному
    slope = np.polyfit(both.city - 1, both.ours - 1, 1)[0]
    corr = both.corr().iloc[0, 1]
    return idx, slope, corr


def plot_routes_vs_city(idx: pd.DataFrame, slope: float, corr: float) -> None:
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.plot(idx.index, idx.city, color=SERIES[1], lw=2, marker="o", ms=4, label="трамвай Москвы, data.mos.ru")
    ax.plot(idx.dropna().index, idx.ours.dropna(), color=SERIES[0], lw=2, marker="o", ms=4, label="наши 9 маршрутов")
    ax.axhline(1, color=TEXT_SECONDARY, lw=0.7)
    ax.axvspan(10.5, 12.5, color=SERIES[1], alpha=0.08, lw=0)
    ax.text(10.6, idx.city.min(), "горизонт\nпрогноза", fontsize=8, color=TEXT_SECONDARY)
    ax.set_xticks(range(1, 13), MONTH_RU)
    ax.set_ylabel("индекс, октябрь = 1")
    ax.legend(loc="lower left")
    ax.set_title(
        f"2025: посадки на эквивалент рабочего дня (поправка на календарь), corr = {corr:.2f}, наклон {slope:.2f}",
        loc="left",
    )
    savefig(fig, "12_routes_vs_city_tram_monthly")


def effects_regression() -> pd.DataFrame:
    """Остатки дня после локального уровня (из s05) против всех внешних факторов сразу."""
    res = pd.read_csv(TABLES / "daily_residuals_weather.csv", parse_dates=["date"])
    school = pd.read_csv(EXT / "school_holidays_moscow.csv", parse_dates=["start", "end"])
    cal = pd.read_csv(EXT / "production_calendar_2025_isdayoff.csv", parse_dates=["date"])
    res["school_holiday"] = 0
    for r in school.itertuples():
        if "летние" in r.name:  # летом школа выключена весь период, эффект уходит в уровень
            continue
        res.loc[res.date.between(r.start, r.end), "school_holiday"] = 1
    res = res.merge(cal, on="date", how="left")
    res["shortened_day"] = (res.isdayoff_code == 2).astype(int)
    off = cal.set_index("date").isdayoff_code.isin([1, 8])
    nxt = off.shift(-1, fill_value=False) & off.shift(-2, fill_value=False) & off.shift(-3, fill_value=False)
    res["before_long_weekend"] = res.date.map(nxt).fillna(False).astype(int) * (res.day_type == "workday")
    res["is_work"] = (res.day_type == "workday").astype(int)
    res["frost"] = np.clip(-10 - res.temp, 0, None)
    formula = ("resid ~ precip + snow + frost + temp_anom + school_holiday:is_work + shortened_day"
               " + before_long_weekend + is_work")
    model = smf.ols(formula, data=res).fit(cov_type="HAC", cov_kwds={"maxlags": 7})
    out = pd.DataFrame({"coef": model.params, "ci_low": model.conf_int()[0], "ci_high": model.conf_int()[1],
                        "p_value": model.pvalues})
    for c in ("coef", "ci_low", "ci_high"):
        out[c.replace("coef", "effect_pct") if c == "coef" else c + "_pct"] = (np.exp(out[c]) - 1) * 100
    print(model.summary().tables[1])
    print(f"n={int(model.nobs)} R2={model.rsquared:.3f}")
    return out


def plot_effects(eff: pd.DataFrame) -> None:
    labels = {
        "precip": "осадки, на 1 мм за день",
        "snow": "снегопад, на 1 см (сверх осадков)",
        "frost": "мороз ниже -10 °C, на 1 °C",
        "temp_anom": "аномалия температуры, на 1 °C",
        "school_holiday:is_work": "школьные каникулы (будни)",
        "shortened_day": "сокращённый предпраздничный день",
        "before_long_weekend": "будний день перед 3+ выходными",
    }
    e = eff.loc[[k for k in labels if k in eff.index]]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    y = np.arange(len(e))
    ax.errorbar(e.effect_pct, y, xerr=[e.effect_pct - e.ci_low_pct, e.ci_high_pct - e.effect_pct],
                fmt="o", color=SERIES[0], ecolor=SERIES[0], elinewidth=1.4, capsize=0, ms=6)
    for yi, (v, p) in enumerate(zip(e.effect_pct, e.p_value, strict=True)):
        ax.text(max(e.ci_high_pct.max(), 0) + 0.5, yi, f"{v:+.1f} %  p={p:.3f}", va="center", fontsize=8,
                color=TEXT_SECONDARY)
    ax.axvline(0, color=TEXT_SECONDARY, lw=0.8)
    ax.set_yticks(y, [labels[k] for k in e.index])
    ax.invert_yaxis()
    ax.set_xlabel("эффект на суточные посадки, % (95 % ДИ, HAC)")
    ax.set_title("Внешние факторы: эффект после удаления локального уровня маршрута и типа дня", loc="left")
    savefig(fig, "13_external_effects")


def main() -> None:
    pd.set_option("display.width", 200)
    weights = day_weights()
    print("day weights:", {k: round(v, 3) for k, v in weights.items()})
    ratios = seasonal_ratios(weights)
    print(ratios.round(3).to_string())
    ratios.round(4).to_csv(TABLES / "seasonal_ratios_nov_dec.csv", index=False)
    idx, slope, corr = routes_vs_city(weights)
    print(idx.round(3).to_string(), f"\nslope={slope:.3f} corr={corr:.3f}")
    idx.round(4).to_csv(TABLES / "routes_vs_city_monthly_index.csv")
    plot_routes_vs_city(idx, slope, corr)
    eff = effects_regression()
    eff.round(4).to_csv(TABLES / "external_effects_regression.csv")
    plot_effects(eff)


if __name__ == "__main__":
    main()
