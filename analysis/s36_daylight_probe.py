"""Световой день и форма суток: эффект заката на доли часовых полос и польза прогнозу.

Гипотеза: чем позже закат, тем больше поездок уходит на поздний вечер (рис. 19 в s15).
Профиль октября переносит октябрьскую форму суток на ноябрь-декабрь, где закат на 0.5-1 ч
раньше, и мог бы получить поправку по закату.

1. Эффект на истории: log(факт / база) часовой полосы в будни минус среднее по полосам того же
   маршрута и дня (так остаётся только форма суток) против сдвига заката к базе. База - медиана
   14 прошлых будней, как в s31. Отдельно для дней с закатом до 18:00 и после: ноябрь-декабрь
   целиком в первом режиме.
2. Польза прогнозу: профиль за 2 недели × exp(γ_полосы · сдвиг заката к окну профиля),
   γ по будням до точки прогноза, суточная сумма профиля сохраняется. Смотрим и на скор
   при выровненном уровне: поправка меняет только форму суток.
Запуск: uv run python analysis/s36_daylight_probe.py
"""

import numpy as np
import pandas as pd
import statsmodels.api as sm

from common import ROOT, TABLES, wape_score
from models import ProfileConfig, profile_forecast
from s06_backtest import load_frame
from s31_weather_probe import CV_FOLDS

PROFILE = ProfileConfig(weeks=2)
BANDS = {"утро 6-9": range(6, 10), "день 10-15": range(10, 16), "вечер 16-19": range(16, 20),
         "поздно 20-23": range(20, 24)}
BAND_OF = {h: b for b, hours in BANDS.items() for h in hours}


def sunset_hours() -> pd.Series:
    sun = pd.read_csv(ROOT / "external" / "daylight_moscow_2025.csv", parse_dates=["date", "sunset"])
    return pd.Series((sun.sunset.dt.hour + sun.sunset.dt.minute / 60).to_numpy(), index=sun.date)


def band_frame(history: pd.DataFrame, sunset: pd.Series) -> pd.DataFrame:
    h = history[history.kind == "workday"].assign(band=history.hour.map(BAND_OF)).dropna(subset=["band"])
    x = (h.groupby(["route", "date", "band"], as_index=False)
         .agg(y=("boardings", "sum"), precip=("precip_day", "first"), holiday=("is_holiday", "first")))
    x = x[~x.holiday].sort_values("date")
    x["sunset"] = x.date.map(sunset)
    g = x.groupby(["route", "band"])
    x["base"] = g["y"].transform(lambda s: s.shift(1).rolling(14, min_periods=4).median())
    x["sunset_base"] = g["sunset"].transform(lambda s: s.shift(1).rolling(14, min_periods=4).mean())
    x = x[(x.y > 0) & (x.base > 0)].copy()
    r = np.log(x.y / x.base)
    x["shape"] = r - r.groupby([x.route, x.date]).transform("mean")
    x["d_sunset"] = x.sunset - x.sunset_base
    return x


def effect(x: pd.DataFrame) -> pd.DataFrame:
    rows = []
    regimes = {"все будни": x.sunset > 0, "закат после 18:00": x.sunset >= 18, "закат до 18:00": x.sunset < 18}
    for regime, sel in regimes.items():
        for band in BANDS:
            d = x[sel & (x.band == band)]
            fit = sm.OLS(d["shape"], sm.add_constant(d[["d_sunset"]].assign(precip=d.precip.fillna(0)))).fit(
                cov_type="cluster", cov_kwds={"groups": d.date.dt.dayofyear})
            lo, hi = fit.conf_int().loc["d_sunset"]
            rows.append({"regime": regime, "band": band, "effect_pct_per_hour": fit.params["d_sunset"] * 100,
                         "ci_low": lo * 100, "ci_high": hi * 100, "p_value": fit.pvalues["d_sunset"],
                         "days": d.date.nunique()})
    return pd.DataFrame(rows)


def band_gamma(x: pd.DataFrame) -> dict:
    if x.date.nunique() < 20:  # на фолде W до 31.01 почти нет будней с базой
        return dict.fromkeys(BANDS, 0.0)
    return {b: float(np.polyfit(x.d_sunset[x.band == b], x["shape"][x.band == b], 1)[0]) for b in BANDS}


def backtest(full: pd.DataFrame, sunset: pd.Series) -> pd.DataFrame:
    rows = []
    for fold in CV_FOLDS:
        origin = pd.Timestamp(fold.origin)
        history = full[full.date <= origin]
        grid = full[(full.date > origin) & (full.date <= pd.Timestamp(fold.end))].reset_index(drop=True)
        y = grid.boardings.to_numpy()
        base = profile_forecast(history, grid.drop(columns="boardings"), origin, PROFILE)
        gamma = band_gamma(band_frame(history, sunset))
        window = sunset[(sunset.index > origin - pd.Timedelta(days=7 * PROFILE.weeks)) & (sunset.index <= origin)]
        shift = (grid.date.map(sunset) - window.mean()).to_numpy()
        p = base * np.exp(grid.hour.map(BAND_OF).map(gamma).fillna(0).to_numpy() * shift)
        day = [grid.route, grid.date]
        p = p * (pd.Series(base).groupby(day).transform("sum") / pd.Series(p).groupby(day).transform("sum")).fillna(1)
        for name, pred in (("профиль 2 нед", base), ("× форма суток по закату", p.to_numpy())):
            rows.append({"fold": fold.name, "variant": name, "wape_score": wape_score(y, pred),
                         "level_aligned": wape_score(y, pred * y.sum() / pred.sum()),
                         "sunset_shift_min": shift.min(), "sunset_shift_max": shift.max(),
                         **{f"gamma_{b}": gamma[b] for b in BANDS}})
    return pd.DataFrame(rows)


def main() -> None:
    pd.set_option("display.width", 220)
    full, sunset = load_frame(), sunset_hours()
    eff = effect(band_frame(full, sunset))
    eff.to_csv(TABLES / "exp_daylight_effect.csv", index=False, float_format="%.4f")
    print(eff.round(3).to_string(index=False), "\n")
    res = backtest(full, sunset)
    res.to_csv(TABLES / "exp_daylight_backtest.csv", index=False, float_format="%.5f")
    for value in ("wape_score", "level_aligned"):
        pv = res.pivot(index="variant", columns="fold", values=value)[[f.name for f in CV_FOLDS]]
        pv.columns = [c[:1] for c in pv.columns]
        pv["среднее"] = pv.mean(axis=1)
        print(value, "\n", pv.round(4).to_string(), "\n")
    nov_dec = sunset["2025-11-01":"2025-12-31"].mean() - sunset["2025-10-18":"2025-10-31"].mean()
    print(f"закат ноября-декабря к окну профиля 18-31.10: {nov_dec:+.2f} ч")


if __name__ == "__main__":
    main()
