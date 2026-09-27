"""Поправки внутри месяца для оценки 2026 года: день недели, школьные каникулы, погода, плавный уровень.

Месячная сумма маршрута остаётся из forecast_year.csv (сезонный индекс), поправки только перераспределяют её
между днями месяца. Каждая оценена по факту января-октября 2025 года (artifacts/actuals.csv):

- профиль дня недели: медиана отношения посадок обычного будня к медиане будней того же маршрута и месяца,
  отдельно для Пн, Вт, Ср, Чт, Пт, нормированная к среднему будню. Обычный будень - рабочий Пн-Пт не перед
  праздником и не после него, не на школьных каникулах и не в пропуске факта (factors.json, gaps). Маршрута 5
  в факте 2025 года нет, ему достаётся профиль сети;
- школьные каникулы: отношение будней каникул к обычным будням того же месяца с поправкой на день недели,
  по сети целиком (взвешено посадками маршрутов), применяется к будням каникул 2026 года;
- погода: коэффициенты модели (artifacts/coefficients.json, precip_day_coef и frost_coef) к осадкам за 6-22 ч
  и морозу ниже -10 °C по средней температуре 6-22 ч, множитель exp(поправка), как в export_components.recompute.
  Погода 2026 года - external/weather_moscow_2026_daily.csv; где её нет, поправки нет;
- плавный уровень: уровень на единицу веса дня стоит в середине месяца и линейно меняется между серединами,
  значения в серединах подобраны так, чтобы суммы месяцев сошлись точно. Ступеньки на границе месяцев нет.
"""

import dataclasses

import numpy as np
import pandas as pd

from common import ROOT

SCHOOL_HOLIDAYS = ROOT / "external" / "school_holidays_moscow.csv"
WEATHER_2026 = ROOT / "external" / "weather_moscow_2026_daily.csv"
FACT_YEAR = "2025"
WORKDAYS = range(5)
FROST_FROM_C = -10.0
# модульные каникулы ноября 2025 - только часть школ, долю не знаем: в оценке эффекта не участвуют
PARTIAL_BREAK = "часть школ"


@dataclasses.dataclass(frozen=True)
class OutlookFactors:
    weekday: pd.DataFrame  # route x dow 0-4, среднее по будням 1
    school_break: float  # множитель будня на каникулах
    school_by_route: pd.Series  # тот же множитель по маршрутам, для отчёта
    break_dates: frozenset[str]  # дни школьных каникул
    weather: pd.Series  # date -> множитель погоды
    precip_day_coef: float
    frost_coef: float


def school_break_dates(path=SCHOOL_HOLIDAYS) -> tuple[frozenset[str], frozenset[str]]:
    """Все дни каникул и дни каникул только части школ."""
    table = pd.read_csv(path)
    every, partial = set(), set()
    for r in table.itertuples():
        days = pd.date_range(r.start, r.end).strftime("%Y-%m-%d")
        (partial if PARTIAL_BREAK in str(r.name) else every).update(days)
    return frozenset(every), frozenset(partial - every)


def _gap_days(periods: list[dict]) -> set[tuple[int, str]]:
    out = set()
    for p in periods:
        for d in pd.date_range(p["from"], p["to"]).strftime("%Y-%m-%d"):
            out.add((int(p["route"]), d))
    return out


def fact_days(actuals: pd.DataFrame, cal: pd.DataFrame, gap_periods: list[dict], breaks: frozenset[str],
              partial: frozenset[str]) -> pd.DataFrame:
    """Будни факта 2025 года по маршрутам с пометками: каникулы, обычный будень."""
    daily = actuals.groupby(["route", "date"], as_index=False).boardings.sum()
    days = cal.assign(prev_type=cal.day_type.shift(1), next_type=cal.day_type.shift(-1))
    daily = daily.merge(days[["date", "dow", "day_type", "prev_type", "next_type"]], on="date")
    daily = daily[(daily.day_type == "workday") & daily.dow.isin(WORKDAYS) & (daily.boardings > 0)]
    near_holiday = (daily.prev_type == "holiday") | (daily.next_type == "holiday")
    gaps = _gap_days(gap_periods)
    in_gap = np.array([(r, d) in gaps for r, d in zip(daily.route, daily.date)])
    clean = ~near_holiday & ~in_gap & ~daily.date.isin(partial)
    return daily[clean].assign(month=lambda f: f.date.str.slice(0, 7), on_break=lambda f: f.date.isin(breaks))


def weekday_profile(days: pd.DataFrame, routes: list[int]) -> pd.DataFrame:
    usual = days[~days.on_break]
    ratio = usual.boardings / usual.groupby(["route", "month"]).boardings.transform("median")
    per_route = ratio.groupby([usual.route, usual.dow]).median().unstack()
    network = ratio.groupby(usual.dow).median()
    profile = per_route.reindex(routes)
    profile = profile.apply(lambda row: row.fillna(network), axis=1)
    return profile.div(profile.mean(axis=1), axis=0)


def school_break_effect(days: pd.DataFrame, weekday: pd.DataFrame) -> tuple[float, pd.Series]:
    """Будни каникул к обычным будням того же маршрута и месяца, оба приведены к среднему дню недели."""
    adj = days.boardings / np.array([weekday.at[r, d] for r, d in zip(days.route, days.dow)])
    frame = days.assign(adj=adj)
    months = frame[frame.on_break].month.unique()
    frame = frame[frame.month.isin(months)]
    means = frame.groupby(["route", "month", "on_break"]).adj.mean().unstack()
    counts = frame[frame.on_break].groupby(["route", "month"]).size()
    means = means.dropna()
    log_ratio = np.log(means[True] / means[False])
    weights = counts.reindex(log_ratio.index)
    by_route = np.exp((log_ratio * weights).groupby(level=0).sum() / weights.groupby(level=0).sum())
    volume = means[False].groupby(level=0).mean().reindex(by_route.index)
    network = float(np.exp((np.log(by_route) * volume).sum() / volume.sum()))
    return network, by_route


def weather_multiplier(weather: pd.DataFrame, precip_day_coef: float, frost_coef: float) -> pd.Series:
    frost = np.clip(FROST_FROM_C - weather.temp_6_22.to_numpy(), 0, None)
    adj = precip_day_coef * weather.precip_6_22.to_numpy() + frost_coef * frost
    return pd.Series(np.exp(adj), index=weather.date.to_numpy())


def build_outlook_factors(actuals: pd.DataFrame, cal: pd.DataFrame, gap_periods: list[dict], routes: list[int],
                          precip_day_coef: float, frost_coef: float, weather: pd.DataFrame | None = None,
                          ) -> OutlookFactors:
    breaks, partial = school_break_dates()
    cal_fact = cal[cal.date.str.startswith(FACT_YEAR)].reset_index(drop=True)
    days = fact_days(actuals, cal_fact, gap_periods, breaks, partial)
    weekday = weekday_profile(days, routes)
    school, school_by_route = school_break_effect(days, weekday)
    weather = pd.read_csv(WEATHER_2026) if weather is None else weather
    return OutlookFactors(weekday=weekday, school_break=school, school_by_route=school_by_route,
                          break_dates=breaks, weather=weather_multiplier(weather, precip_day_coef, frost_coef),
                          precip_day_coef=precip_day_coef, frost_coef=frost_coef)


def smooth_daily(dates: pd.Series, weights: np.ndarray, totals: np.ndarray) -> np.ndarray:
    """Дневные значения: вес дня × уровень, линейный между серединами месяцев, суммы месяцев = totals.

    dates - дни подряд по возрастанию, totals - сумма месяца для каждого дня (одинаковая внутри месяца)."""
    month = dates.str.slice(0, 7).to_numpy()
    t = pd.to_datetime(dates).map(pd.Timestamp.toordinal).to_numpy().astype(float)
    labels, first = np.unique(month, return_index=True)
    order = np.argsort(first)
    labels = labels[order]
    nodes = np.array([t[month == m].mean() for m in labels])
    target = np.array([totals[month == m][0] for m in labels])
    # базис линейной интерполяции: у каждого узла своя «шляпка», за краями уровень постоянный
    basis = np.column_stack([np.interp(t, nodes, np.eye(len(labels))[k]) for k in range(len(labels))])
    member = (month[:, None] == labels[None, :]).astype(float)
    system = member.T @ (basis * weights[:, None])
    level = np.linalg.solve(system, target)
    if (level < 0).any():  # на всякий случай: без отрицательных уровней, тогда уровень постоянный в месяце
        level = target / (member.T @ weights)
        daily = weights * (member @ level)
    else:
        daily = weights * (basis @ level)
    sums = member.T @ daily
    scale = np.divide(target, sums, out=np.zeros_like(target), where=sums > 0)
    return daily * (member @ scale)
