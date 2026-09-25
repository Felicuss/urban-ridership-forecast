"""Погодная поправка на бэктесте: как в s10 и нормированная на погоду окна профиля.

В s10 поправка умножает прогноз на exp(adj) по фактической погоде горизонта. Но база -
медиана посадок за последние 2 недели перед точкой прогноза, а в эти дни тоже шли дожди,
так что поправка учитывает погоду второй раз и занижает уровень. Нормированный вариант
делит множитель ячейки на медиану множителей тех дней окна, из которых собрана её база
(тот же тип дня и час).

Сравниваем на фолдах s06 и на фолде W (февраль-март, есть морозы) профиль за 2 недели:
без погоды, с поправкой как в s10, с нормированной и с нормированной, где коэффициент
осадков оценён только по данным до точки прогноза. Для каждого варианта считаем обычный
скор и скор при уровне, выровненном по факту: разница между ними отделяет влияние погоды
на распределение посадок по дням от сдвига общего уровня.

Отдельно оцениваем сам эффект осадков по сезонам: дождь и снег зимой раздельно.
Запуск: uv run python analysis/s31_weather_probe.py
"""

import numpy as np
import pandas as pd

from common import TABLES, wape_score
from models import ProfileConfig, profile_forecast
from s06_backtest import FOLDS, Fold, load_frame

CV_FOLDS = [*FOLDS, Fold("W: до 31.01 -> февраль-март", "2025-01-31", "2025-03-31")]
PROFILE = ProfileConfig(weeks=2)
PRECIP_DAY, PRECIP_HOUR, FROST = -0.0074, -0.035, -0.0178  # как в s10, оценены на январе-октябре


def weather_log(df: pd.DataFrame, precip_day: float, precip_hour: float) -> np.ndarray:
    return (precip_day * df.precip_day.fillna(0)
            + precip_hour * df.precipitation.fillna(0).clip(0, 3)
            + FROST * np.clip(-10 - df.temp_day.fillna(0), 0, None)).to_numpy()


def window_norm(history: pd.DataFrame, origin: pd.Timestamp, precip_day: float, precip_hour: float) -> pd.Series:
    """Медианный погодный множитель дней окна профиля по типу дня и часу."""
    days = history[(history.date > origin - pd.Timedelta(days=7 * PROFILE.weeks)) & ~history.is_holiday]
    days = days.drop_duplicates(["date", "hour"])
    m = np.exp(weather_log(days, precip_day, precip_hour))
    return pd.Series(m, index=days.index).groupby([days.kind, days.hour]).median()


def causal_precip_coef(history: pd.DataFrame) -> float:
    """Эффект мм осадков на дневные посадки только по данным до точки прогноза.

    База дня - медиана того же маршрута и типа дня за предыдущие 14 дней, эффект -
    наклон log(факт / база) по осадкам за 06-22 без свободного члена.
    """
    daily = (history.groupby(["route", "date", "kind"], as_index=False)
             .agg(y=("boardings", "sum"), precip=("precip_day", "first"), holiday=("is_holiday", "first")))
    daily = daily[~daily.holiday].sort_values("date")
    base = (daily.groupby(["route", "kind"])["y"]
            .transform(lambda s: s.shift(1).rolling(14, min_periods=4).median()))
    ok = (daily.y > 0) & (base > 0)
    r = np.log(daily.y[ok] / base[ok])
    x = daily.precip[ok].fillna(0)
    r = r - r.mean()
    return float((x * r).sum() / (x * x).sum())


def seasonal_effect(full: pd.DataFrame) -> pd.DataFrame:
    """Эффект мм осадков на дневные посадки по сезонам, дождь и снег зимой раздельно.

    База та же, что в causal_precip_coef; ошибки кластеризованы по дню, потому что
    все маршруты одного дня видят одну погоду.
    """
    import statsmodels.api as sm

    daily = (full.groupby(["route", "date", "kind"], as_index=False)
             .agg(y=("boardings", "sum"), precip=("precip_day", "first"), temp=("temp_day", "first"),
                  holiday=("is_holiday", "first")))
    daily = daily[~daily.holiday].sort_values("date")
    daily["base"] = (daily.groupby(["route", "kind"])["y"]
                     .transform(lambda s: s.shift(1).rolling(14, min_periods=4).median()))
    d = daily[(daily.y > 0) & (daily.base > 0)]
    month = d.date.dt.month
    groups = {
        "апрель-октябрь": month.between(4, 10),
        "январь-март, все осадки": month <= 3,
        "январь-март, t < 0 (снег)": (month <= 3) & (d.temp < 0),
        "январь-март, t >= 0 (дождь, мокрый снег)": (month <= 3) & (d.temp >= 0),
    }
    rows = []
    for name, sel in groups.items():
        x = d[sel]
        fit = sm.OLS(np.log(x.y / x.base), sm.add_constant(x.precip.fillna(0))).fit(
            cov_type="cluster", cov_kwds={"groups": x.date.dt.dayofyear})
        lo, hi = fit.conf_int().iloc[1]
        rows.append({"period": name, "effect_pct_per_mm": fit.params.iloc[1] * 100, "ci_low": lo * 100,
                     "ci_high": hi * 100, "p_value": fit.pvalues.iloc[1], "days": x.date.nunique()})
    return pd.DataFrame(rows)


def main() -> None:
    full = load_frame()
    season = seasonal_effect(full)
    season.to_csv(TABLES / "exp_weather_season.csv", index=False)
    print(season.round(3).to_string(index=False), "\n")
    rows = []
    for fold in CV_FOLDS:
        origin = pd.Timestamp(fold.origin)
        history = full[full.date <= origin]
        grid = full[(full.date > origin) & (full.date <= pd.Timestamp(fold.end))].reset_index(drop=True)
        y = grid.boardings.to_numpy()
        base = profile_forecast(history, grid.drop(columns="boardings"), origin, PROFILE)

        k = causal_precip_coef(history)
        scale = k / PRECIP_DAY  # часовой коэффициент меняем в той же пропорции
        variants = {"без погоды": base,
                    "погода как в s10": base * np.exp(weather_log(grid, PRECIP_DAY, PRECIP_HOUR))}
        for name, pd_coef, ph_coef in (("нормированная", PRECIP_DAY, PRECIP_HOUR),
                                       ("нормированная, коэффициент до origin", k, PRECIP_HOUR * scale)):
            norm = window_norm(history, origin, pd_coef, ph_coef)
            n = norm.reindex(pd.MultiIndex.from_arrays([grid.kind, grid.hour])).fillna(1.0).to_numpy()
            variants[name] = base * np.exp(weather_log(grid, pd_coef, ph_coef)) / n

        for name, p in variants.items():
            rows.append({"fold": fold.name, "variant": name, "wape_score": wape_score(y, p),
                         "level_aligned": wape_score(y, p * y.sum() / p.sum()),
                         "bias_pct": (p.sum() / y.sum() - 1) * 100, "precip_coef": k if "origin" in name else None})

    res = pd.DataFrame(rows)
    res.to_csv(TABLES / "exp_weather_normalized.csv", index=False)
    pivot = res.pivot_table(index="variant", columns="fold", values="wape_score")
    pivot["среднее"] = pivot.mean(axis=1)
    aligned = res.pivot_table(index="variant", columns="fold", values="level_aligned")
    aligned["среднее"] = aligned.mean(axis=1)
    pd.set_option("display.width", 200)
    print("WAPE-score\n", pivot.round(4).to_string())
    print("\nпри выровненном уровне\n", aligned.round(4).to_string())
    print("\nсмещение суммы, %\n", res.pivot_table(index="variant", columns="fold", values="bias_pct").round(1).to_string())
    print("\nкоэффициент осадков до origin:", res.dropna(subset=["precip_coef"]).set_index("fold").precip_coef.round(4).to_dict())


if __name__ == "__main__":
    main()
