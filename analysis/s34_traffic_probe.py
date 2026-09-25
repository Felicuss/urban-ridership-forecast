"""Трафик и посадки: помесячная загруженность дорог (data.mos.ru 62525) и баллы ЦОДД из постов.

Гипотеза: загруженность дорог показывает, сколько ездит город. В месяцы с более загруженными
дорогами больше и поездок на трамвае, который идёт по своим путям и в пробках не стоит.
Если так, загруженность месяца задаёт уровень посадок, как городской пассажиропоток в s18.

1. Эффект на истории по месяцам: изменение log(трамвай Москвы на эквивалент рабочего дня)
   за месяц против изменения балла и процента загруженности, 2022-2025, HAC-ошибки.
   С эффектами года и месяца видно, есть ли связь сверх обычной сезонности.
2. Эффект на истории по дням: log(факт / база) маршрута против балла ЦОДД в тот же будний
   день, база и кластеры как в s31. Второй вариант - балл минус его медиана за ±15 дней:
   так видно, двигают ли посадки сами дневные колебания пробок, а не сезонный уровень.
3. Польза прогнозу: профиль за 2 недели × exp(γ·ΔT), где ΔT - загруженность месяца горизонта
   минус загруженность месяца отсечки, γ - наклон из п. 1 только по месяцам до отсечки.
   Балл и процент усредняем в логарифме, чтобы не выбирать показатель по бэктесту.
   Трафик сравниваем и смешиваем с уровнем по сезонности прошлых лет (как в s30) и по
   городскому трамваю 2025 года (как в s18).
Запуск: uv run python analysis/s34_traffic_probe.py (после s33)
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

from common import ROOT, SERIES, TABLES, TEXT_SECONDARY, savefig, wape_score
from models import ProfileConfig, profile_forecast
from s06_backtest import load_frame
from s09_external_factors import calendar_table, day_weights
from s31_weather_probe import CV_FOLDS

EXT = ROOT / "external"
PROFILE = ProfileConfig(weeks=2)
PAST_YEARS = [2019, 2022, 2023, 2024]  # как в s30: 2020-2021 ковид, 2025 - год прогноза
AMPLITUDE = 0.83  # наши маршруты к городскому трамваю, как в s10 и s30
MEASURES = ["congestion_score", "congestion_pct"]


def city_tram_monthly() -> pd.DataFrame:
    """log посадок трамвая Москвы на эквивалент рабочего дня и загруженность дорог по месяцам."""
    w = day_weights()
    cal = calendar_table().assign(w=lambda c: c.kind.map(w))
    w_days = cal.groupby([cal.date.dt.year.rename("year"), cal.date.dt.month.rename("month")])["w"].sum()
    tram = pd.read_csv(EXT / "datamos_62521_monthly_ridership.csv").query("transport == 'Трамвай'")
    tram = tram.join(w_days.rename("w_days"), on=["year", "month"], how="inner")
    tram["lr"] = np.log(tram.passengers / tram.w_days)
    cong = pd.read_csv(EXT / "datamos_62525_monthly_congestion.csv")
    out = tram.merge(cong, on=["year", "month"], how="left")[["year", "month", "lr", *MEASURES]]
    return out.sort_values(["year", "month"]).reset_index(drop=True)


def traffic_gamma(monthly: pd.DataFrame, until: pd.Timestamp) -> dict:
    """Наклон месячного изменения log посадок трамвая по изменению загруженности, 2022 - месяц отсечки."""
    d = monthly[(monthly.year >= 2022) & (monthly.year * 100 + monthly.month <= until.year * 100 + until.month)]
    dy = d.lr.diff().iloc[1:]
    return {m: float(np.polyfit(d[m].diff().iloc[1:], dy, 1)[0]) for m in MEASURES}


def ours_monthly(full: pd.DataFrame, monthly: pd.DataFrame) -> pd.DataFrame:
    """log посадок наших 9 маршрутов на эквивалент рабочего дня, февраль-октябрь 2025.

    Январь не берём, как в s09: неделя праздников искажает его сильнее, чем городской ряд.
    """
    d = full.groupby(["date", "day_type"], as_index=False)["boardings"].sum()
    d["w"] = d.day_type.map(day_weights())
    m = d.groupby(d.date.dt.month).agg(y=("boardings", "sum"), w=("w", "sum"))
    out = pd.DataFrame({"month": m.index, "lr": np.log(m.y / m.w).to_numpy()})
    out = out.merge(monthly[monthly.year == 2025][["month", *MEASURES]], on="month")
    return out[out.month >= 2]


def monthly_effect(monthly: pd.DataFrame, ours: pd.DataFrame) -> list[dict]:
    x = monthly[monthly.year.between(2022, 2025)].copy()
    for df in (x, ours):
        for c in ["lr", *MEASURES]:
            df[f"d_{c}"] = df[c].diff()
    rows = []
    for m in MEASURES:
        specs = {
            ("data.mos.ru 62525, трамвай Москвы 2022-2025", "изменение за месяц"):
                (f"d_lr ~ d_{m}", x.dropna(subset=["d_lr"]), f"d_{m}"),
            ("data.mos.ru 62525, трамвай Москвы 2022-2025", "изменение за месяц, без января"):
                (f"d_lr ~ d_{m}", x[x.month != 1].dropna(subset=["d_lr"]), f"d_{m}"),
            ("data.mos.ru 62525, трамвай Москвы 2022-2025", "уровень, эффекты года и месяца"):
                (f"lr ~ {m} + C(year) + C(month)", x, m),
            ("data.mos.ru 62525, наши 9 маршрутов, февраль-октябрь 2025", "изменение за месяц"):
                (f"d_lr ~ d_{m}", ours.dropna(subset=["d_lr"]), f"d_{m}"),
        }
        for (source, spec), (formula, data, term) in specs.items():
            cov = {"cov_type": "HC1"} if "наши" in source else {"cov_type": "HAC", "cov_kwds": {"maxlags": 3}}
            fit = smf.ols(formula, data=data).fit(**cov)
            lo, hi = fit.conf_int().loc[term]
            unit = "1 балл" if m == "congestion_score" else "1 п.п. загруженности"
            rows.append({"source": source, "measure": m, "spec": spec, "unit": unit,
                         "effect_pct": fit.params[term] * 100, "ci_low": lo * 100, "ci_high": hi * 100,
                         "p_value": fit.pvalues[term], "n": int(fit.nobs)})
    return rows


def codd_daily() -> pd.DataFrame:
    """Максимальный за день балл ЦОДД из постов и его отклонение от медианы соседних ±15 дней."""
    p = pd.read_csv(EXT / "traffic_codd_posts_2025.csv", parse_dates=["ts"]).dropna(subset=["score"])
    s = p.groupby(p.ts.dt.normalize().rename("date"))["score"].max()
    near = pd.Timedelta(days=15)
    local = [s[(s.index >= d - near) & (s.index <= d + near) & (s.index != d)].median() for d in s.index]
    return pd.DataFrame({"codd_score": s, "codd_dev": s - np.array(local)}).reset_index()


def daily_ratio(full: pd.DataFrame) -> pd.DataFrame:
    """log(факт / база) по маршруту и дню, база - медиана 14 прошлых дней того же типа, как в s31."""
    daily = (full.groupby(["route", "date", "kind"], as_index=False)
             .agg(y=("boardings", "sum"), precip=("precip_day", "first"), holiday=("is_holiday", "first"),
                  dow=("dow", "first")))
    daily = daily[~daily.holiday].sort_values("date")
    daily["base"] = (daily.groupby(["route", "kind"])["y"]
                     .transform(lambda s: s.shift(1).rolling(14, min_periods=4).median()))
    d = daily[(daily.y > 0) & (daily.base > 0) & (daily.kind == "workday")].copy()
    d["r"] = np.log(d.y / d.base)
    return d


def fit_daily(d: pd.DataFrame, term: str):
    x = pd.DataFrame({term: d[term], "precip": d.precip.fillna(0)})
    x = x.join(pd.get_dummies(d.dow, prefix="dow", drop_first=True, dtype=float))  # вечер пятницы тяжелее
    return sm.OLS(d.r, sm.add_constant(x)).fit(cov_type="cluster", cov_kwds={"groups": d.date.dt.dayofyear})


def daily_effect(ratio: pd.DataFrame, codd: pd.DataFrame) -> list[dict]:
    d = ratio.merge(codd, on="date")
    rows = []
    for term, spec in (("codd_score", "балл дня"), ("codd_dev", "балл дня минус медиана ±15 дней")):
        x = d.dropna(subset=[term])
        fit = fit_daily(x, term)
        lo, hi = fit.conf_int().loc[term]
        rows.append({"source": "посты ЦОДД в t.me/DtOperativno, будни 2025", "measure": "codd_score", "spec": spec,
                     "unit": "1 балл", "effect_pct": fit.params[term] * 100, "ci_low": lo * 100,
                     "ci_high": hi * 100, "p_value": fit.pvalues[term], "n": x.date.nunique()})
    return rows


def backtest(full: pd.DataFrame, monthly: pd.DataFrame, ratio: pd.DataFrame, codd: pd.DataFrame) -> pd.DataFrame:
    lr = monthly.set_index(["year", "month"]).lr
    cong = monthly[monthly.year == 2025].set_index("month")
    rows = []
    for fold in CV_FOLDS:
        origin = pd.Timestamp(fold.origin)
        history = full[full.date <= origin]
        grid = full[(full.date > origin) & (full.date <= pd.Timestamp(fold.end))].reset_index(drop=True)
        y = grid.boardings.to_numpy()
        base = profile_forecast(history, grid.drop(columns="boardings"), origin, PROFILE)
        month = grid.date.dt.month

        gamma = traffic_gamma(monthly, origin)
        by_measure = {m: (gamma[m] * (month.map(cong[m]) - cong[m][origin.month])).to_numpy() for m in MEASURES}
        traffic = (by_measure["congestion_score"] + by_measure["congestion_pct"]) / 2
        seasonal = AMPLITUDE * month.map(lambda m: np.median(
            [lr[(yy, m)] - lr[(yy, origin.month)] for yy in PAST_YEARS])).to_numpy()
        city = month.map(lambda m: lr[(2025, m)] - lr[(2025, origin.month)]).to_numpy()

        # дневной балл ЦОДД: отклонение от медианы 4 недель до отсечки, коэффициент по дням до отсечки
        hist_days = ratio[ratio.date <= origin].merge(codd, on="date")
        beta = fit_daily(hist_days, "codd_score").params["codd_score"] if hist_days.date.nunique() >= 20 else 0.0
        s = codd.set_index("date").codd_score
        s0 = s[(s.index > origin - pd.Timedelta(days=28)) & (s.index <= origin)].median()
        day_adj = beta * (grid.date.map(s) - s0).fillna(0).to_numpy() if pd.notna(s0) else np.zeros(len(grid))

        variants = {
            "профиль 2 нед": 0.0,
            "× трафик 62525 (балл и процент)": traffic,
            "× трафик 62525, только балл": by_measure["congestion_score"],
            "× трафик 62525, только процент": by_measure["congestion_pct"],
            "× сезон прошлых лет (как s30)": seasonal,
            "× сезон прошлых лет и трафик": (seasonal + traffic) / 2,
            "× городской трамвай 2025 (как s18)": city,
            "× городской трамвай 2025 и трафик": (city + traffic) / 2,
            "× дневной балл ЦОДД": day_adj,
        }
        for name, log_mult in variants.items():
            p = base * np.exp(log_mult)
            rows.append({"fold": fold.name, "variant": name, "wape_score": wape_score(y, p),
                         "level_aligned": wape_score(y, p * y.sum() / p.sum()),
                         "bias_pct": (p.sum() / y.sum() - 1) * 100,
                         "gamma_score": gamma["congestion_score"], "gamma_pct": gamma["congestion_pct"]})
    return pd.DataFrame(rows)


def novdec_levels(monthly: pd.DataFrame) -> dict:
    """Множители ноября и декабря 2025 к октябрю по трафику, γ по месяцам до октября включительно."""
    gamma = traffic_gamma(monthly, pd.Timestamp("2025-10-31"))
    cong = monthly[monthly.year == 2025].set_index("month")
    out = {"gamma_score": round(gamma["congestion_score"], 4), "gamma_pct": round(gamma["congestion_pct"], 5)}
    for m, name in ((11, "nov"), (12, "dec")):
        log_mult = np.mean([gamma[c] * (cong[c][m] - cong[c][10]) for c in MEASURES])
        out[f"traffic_level_{name}"] = round(float(np.exp(log_mult)), 4)
    return out


def plot_traffic(monthly: pd.DataFrame, res: pd.DataFrame) -> None:
    x = monthly[monthly.year.between(2022, 2025)].copy()
    x["d_lr"] = x.lr.diff() * 100
    x["d_pct"] = x.congestion_pct.diff()
    x = x.dropna(subset=["d_lr"])
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.8))
    ax = axes[0]
    ax.scatter(x.d_pct, x.d_lr, color=SERIES[0], s=36, zorder=3, edgecolor="white", linewidth=1)
    k, b = np.polyfit(x.d_pct, x.d_lr, 1)
    xs = np.linspace(x.d_pct.min(), x.d_pct.max(), 2)
    ax.plot(xs, k * xs + b, color=TEXT_SECONDARY, lw=1.2)
    for _, r in x[x.year == 2025].iterrows():
        if r.month in (1, 11, 12):
            ax.annotate(f"{int(r.month):02d}.2025", (r.d_pct, r.d_lr), xytext=(5, 3), textcoords="offset points",
                        fontsize=8, color=TEXT_SECONDARY)
    ax.axhline(0, color=TEXT_SECONDARY, lw=0.6)
    ax.axvline(0, color=TEXT_SECONDARY, lw=0.6)
    ax.set_xlabel("изменение загруженности дорог за месяц, п.п. (data.mos.ru 62525)")
    ax.set_ylabel("изменение посадок трамвая Москвы, %")
    ax.set_title(f"Трамвай Москвы и загруженность дорог, 2022-2025: {k:+.2f} % на п.п.", loc="left")

    ax = axes[1]
    variants = ["профиль 2 нед", "× трафик 62525 (балл и процент)", "× сезон прошлых лет (как s30)",
                "× сезон прошлых лет и трафик"]
    folds = list(dict.fromkeys(res.fold))
    ypos = np.arange(len(folds))
    for i, v in enumerate(variants):
        s = res[res.variant == v].set_index("fold").wape_score.reindex(folds)
        ax.scatter(s, ypos + (i - 1.5) * 0.12, color=SERIES[i], s=40, zorder=3, label=v)
    ax.set_yticks(ypos, [f[:1] for f in folds])
    ax.invert_yaxis()
    ax.set_xlabel("WAPE-score (больше - лучше)")
    ax.set_ylabel("фолд")
    ax.legend(loc="upper right")
    ax.set_title("Бэктест: уровень по трафику на фолдах", loc="left")
    fig.tight_layout()
    savefig(fig, "20_traffic_level")


def main() -> None:
    pd.set_option("display.width", 220)
    monthly = city_tram_monthly()
    full = load_frame()
    ratio, codd = daily_ratio(full), codd_daily()

    effect = pd.DataFrame(monthly_effect(monthly, ours_monthly(full, monthly)) + daily_effect(ratio, codd))
    effect.to_csv(TABLES / "exp_traffic_effect.csv", index=False, float_format="%.4f")
    print(effect.round(4).to_string(index=False), "\n")

    res = backtest(full, monthly, ratio, codd)
    plot_traffic(monthly, res)
    res.to_csv(TABLES / "exp_traffic_backtest.csv", index=False, float_format="%.5f")
    order = list(dict.fromkeys(res.variant))
    for value, title in (("wape_score", "WAPE-score"), ("level_aligned", "при выровненном уровне"),
                         ("bias_pct", "смещение суммы, %")):
        pv = res.pivot(index="variant", columns="fold", values=value).loc[order, [f.name for f in CV_FOLDS]]
        pv.columns = [c[:1] for c in pv.columns]
        pv["среднее"] = pv.mean(axis=1)
        print(title, "\n", pv.round(1 if value == "bias_pct" else 4).to_string(), "\n")
    print("ноябрь-декабрь 2025 по трафику:", novdec_levels(monthly))


if __name__ == "__main__":
    main()
