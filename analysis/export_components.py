"""Компоненты прогноза для сервиса: база и заготовки правил s10 на каждую ячейку маршрут × дата × час.

Одного JSON коэффициентов сервису мало: apply_rules не только умножает, но и заменяет значения
целиком (выходные 7 и 50, маршрут 5, 31.12). Поэтому на каждую ячейку пишем обе базы, календарные
флаги, форму суток маршрута 5 и погоду, а сама формула повторена в recompute(). Сервис на Java
считает по той же формуле, эталонные тесты сверяют её с s10.make_forecast (tests/test_artifacts.py).
"""

import dataclasses

import numpy as np
import pandas as pd

import s10_forecast as s10

WEEKEND_ROUTES = (7, 50)
PRE_NEW_YEAR = pd.to_datetime(["2025-12-29", "2025-12-30"])
NEW_YEAR_EVE = pd.Timestamp("2025-12-31")
# доли выходных маршрута 5 к будню, как в s10.apply_rules
ROUTE5_SATURDAY, ROUTE5_SUNDAY = 0.6, 0.5


def restored_base(hist: pd.DataFrame, grid: pd.DataFrame, base: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """База выходных 7 и 50 по полной трассе: уровень будней × весеннее отношение × форма суток.

    Считается для всех выходных ячеек этих маршрутов, а дату возврата выбирает формула, поэтому
    её можно двигать ползунком.
    """
    g = grid
    wd_daily = pd.Series(base, index=g.index)[g.kind == "workday"].groupby([g.route, g.date]).sum()
    wd_level = wd_daily.groupby(level=0).median()
    out = np.zeros(len(g))
    restorable = np.zeros(len(g), dtype=bool)
    for route in WEEKEND_ROUTES:
        ratios, shape = s10.spring_weekend(hist, route)
        sel = ((g.route == route) & g.kind.isin(["saturday", "sunday"])).to_numpy()
        kinds = g.kind[sel].to_numpy()
        day_total = wd_level[route] * np.array([ratios[k] for k in kinds])
        sh = shape.reindex(pd.MultiIndex.from_arrays([kinds, g.hour[sel].to_numpy()])).fillna(0).to_numpy()
        out[sel] = day_total * sh
        restorable |= sel
    return out, restorable


def route5_shape(hist: pd.DataFrame, grid: pd.DataFrame) -> np.ndarray:
    """Доля часа в сутках будня маршрута 50 за 4 недели: форма суток нового маршрута 5."""
    prof50 = hist[(hist.route == 50) & (hist.date > hist.date.max() - pd.Timedelta(days=28))]
    sh = prof50.groupby(["kind", "hour"])["boardings"].mean()
    sh = sh / sh.xs("workday").sum()
    r5 = (grid.route == 5).to_numpy()
    out = np.zeros(len(grid))
    out[r5] = sh.xs("workday").reindex(grid.hour[r5].to_numpy()).to_numpy()
    return out


def build_components(c: s10.Coefficients) -> pd.DataFrame:
    hist = s10.load_history()
    grid = s10.forecast_grid()
    base = s10.base_profile(hist, grid, c.profile_weeks)
    base_restored, restorable = restored_base(hist, grid, base)
    g = grid
    return pd.DataFrame({
        "route": g.route, "date": g.date.dt.strftime("%Y-%m-%d"), "hour": g.hour, "dow": g.dow,
        "kind": g.kind,
        "is_holiday": g.is_holiday.astype(int),
        "is_working_saturday": ((g.dow == 5) & (g.day_type == "workday")).astype(int),
        "is_pre_new_year": g.date.isin(PRE_NEW_YEAR).astype(int),
        "is_new_year_eve": (g.date == NEW_YEAR_EVE).astype(int),
        "base": base, "base_restored": base_restored, "restorable": restorable.astype(int),
        "route5_shape": route5_shape(hist, grid),
        "precip_day": g.precip_day.fillna(0), "precip_hour": g.precipitation.fillna(0),
        "temp_day": g.temp_day.fillna(0),
    })


def _on_or_after(dates: pd.Series, when: str) -> np.ndarray:
    return (pd.to_datetime(dates) >= pd.Timestamp(when)).to_numpy()


def recompute(comp: pd.DataFrame, c: s10.Coefficients) -> np.ndarray:
    """Та же арифметика, что в s10.apply_rules, только по готовым столбцам. Эталон для сервиса."""
    date = pd.to_datetime(comp.date)
    month = date.dt.month.to_numpy()
    hour = comp.hour.to_numpy()
    level = np.where(month == 11, c.level_nov, c.level_dec)
    holiday = comp.is_holiday.to_numpy() == 1
    weekday_holiday = holiday & (comp.dow.to_numpy() < 5)
    restored = (comp.restorable.to_numpy() == 1) & _on_or_after(comp.date, c.weekend_restore_date)

    regular = comp.base.to_numpy() * level
    regular = regular * np.where(weekday_holiday, c.holiday_to_sunday, 1.0)
    regular = regular * np.where(comp.is_working_saturday.to_numpy() == 1, c.working_saturday, 1.0)
    regular = regular * np.where(comp.is_pre_new_year.to_numpy() == 1, c.last_workdays_dec, 1.0)
    weekend = comp.base_restored.to_numpy() * (level * np.where(holiday, c.holiday_to_sunday, 1.0))
    pred = np.where(restored, weekend, regular)

    eve = comp.is_new_year_eve.to_numpy() == 1
    free = eve & (hour >= c.dec31_free_from_hour)
    pred = pred * np.where(eve, c.dec31_day, 1.0)
    pred = np.where(free, 0.0, pred)
    t1 = (comp.route.to_numpy() == 7) & _on_or_after(comp.date, c.t1_start)
    pred = pred * np.where(t1, c.t1_route7, 1.0)

    r5 = comp.route.to_numpy() == 5
    ts = date + pd.to_timedelta(comp.hour, unit="h")
    kind = comp.kind.to_numpy()
    day_ratio = np.select([kind == "saturday", kind == "sunday"], [ROUTE5_SATURDAY, ROUTE5_SUNDAY], 1.0)
    launched = r5 & (ts >= pd.Timestamp(c.route5_start)).to_numpy() & c.route5_on
    route5 = c.route5_workday * comp.route5_shape.to_numpy() * day_ratio
    pred = np.where(r5, np.where(launched & ~free, route5, 0.0), pred)

    if c.weather:
        adj = (c.precip_day_coef * comp.precip_day.to_numpy()
               + c.hour_precip_coef * np.clip(comp.precip_hour.to_numpy(), 0, 3)
               + c.frost_coef * np.clip(-10 - comp.temp_day.to_numpy(), 0, None))
        pred = pred * np.exp(adj)
    return np.clip(pred, 0, None)


def scenario_coefficients(default: s10.Coefficients) -> dict[str, s10.Coefficients]:
    """Наборы для эталонных тестов: каждый двигает свои правила, чтобы расхождение формулы было видно."""
    return {
        "default": default,
        "shifted": dataclasses.replace(
            default, level_nov=1.05, level_dec=0.97, holiday_to_sunday=0.9, working_saturday=0.8,
            last_workdays_dec=0.7, dec31_day=0.8, dec31_free_from_hour=22, weekend_restore_date="2025-11-29",
            t1_start="2025-11-20", t1_route7=0.93, route5_start="2025-12-20 07:00", route5_workday=8000.0),
        "weather": dataclasses.replace(default, weather=True),
        "no_events": dataclasses.replace(default, route5_on=False, weekend_restore_date="2026-01-01",
                                         dec31_free_from_hour=24),
        "early_restore": dataclasses.replace(default, weekend_restore_date="2025-11-01", t1_start="2025-11-01",
                                             t1_route7=0.9, route5_start="2025-12-01 00:00"),
    }
