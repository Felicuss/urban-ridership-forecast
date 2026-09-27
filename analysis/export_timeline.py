"""Шкала времени интерфейса: 01.01.2025 - 31.10.2026, чтобы смотреть любую дату, а не только горизонт.

- январь-октябрь 2025 - факт: успешные валидации по часам из данных организаторов;
- ноябрь-декабрь 2025 - почасовой прогноз модели (forecast_components.csv, пересчитывается сценарием);
- январь-октябрь 2026 - оценка: месячный прогноз года (forecast_year.csv, сезонный индекс) раскладывается
  по дням и по часам. Сумма месяца маршрута не меняется, внутри месяца вес дня - произведение поправок
  (analysis/outlook_factors.py, все оценены по факту 2025 года): тип дня (суббота, воскресенье и праздник
  к будню - из прогноза декабря 2025), день недели Пн-Пт, школьные каникулы, погода Open-Meteo по коэффициентам
  модели; уровень плавно меняется между серединами месяцев, без ступеньки на границе. По часам - форма суток
  маршрута из прогноза декабря 2025 (1-28.12, без предновогодних дней).

Календарь 2025 - как в модели (calendar_ru, рабочая суббота 01.11), 2026 - официальный производственный
календарь isdayoff.ru с переносами (09.01, 09.03, 11.05 и др.), названия праздников из пакета holidays.

Валидации в часы, когда маршрут не работает, организаторы на встрече 26.09.2026 назвали проверкой
оборудования: их надо отбрасывать. Часы работы - от первого отправления за 30 минут до последнего через час
по расписанию transport.mos.ru (external/transport_mos_schedule.csv), будни и выходные вместе, чтобы не
потерять настоящие поздние рейсы. В факт такие часы идут нулём, их число пишется в factors.json.
"""

import datetime as dt

import holidays
import numpy as np
import pandas as pd

from calendar_ru import calendar_frame
from common import ROOT, ROUTES, load_labels
from outlook_factors import OutlookFactors, smooth_daily

TIMELINE_START, TIMELINE_END = "2025-01-01", "2026-10-31"
FACT_END, FORECAST_END = "2025-10-31", "2025-12-31"
SHAPE_FROM, SHAPE_TO = "2025-12-01", "2025-12-28"
ROUTE5_SHAPE_FROM = "2025-12-17"
HOURS = 24
SCHEDULE = ROOT / "external" / "transport_mos_schedule.csv"
BEFORE_FIRST_MIN = 30
AFTER_LAST_MIN = 60
# ночные отправления до полудня относятся к прошлым суткам: 01:36 - это 25:36
NEXT_DAY_BEFORE_MIN = 12 * 60


def source_of(date: pd.Timestamp) -> str:
    if date <= pd.Timestamp(FACT_END):
        return "fact"
    return "forecast" if date <= pd.Timestamp(FORECAST_END) else "outlook"


def calendar_2026() -> pd.DataFrame:
    codes = pd.read_csv(ROOT / "external" / "production_calendar_2026_isdayoff.csv", parse_dates=["date"])
    names = holidays.country_holidays("RU", years=2026)
    rows = []
    for r in codes.itertuples():
        d = r.date.date()
        off = r.isdayoff_code in (1, 8)
        dow = d.weekday()
        if off:
            day_type = "holiday" if dow < 5 else ("saturday" if dow == 5 else "sunday")
        else:
            day_type = "workday"
        name = names.get(d) or ("Выходной, перенос" if off and dow < 5 else None)
        rows.append({"date": r.date, "dow": dow, "day_type": day_type, "day_off": off, "holiday": name})
    return pd.DataFrame(rows)


def timeline_calendar() -> pd.DataFrame:
    y2025 = calendar_frame("2025-01-01", "2025-12-31")
    y2025 = pd.DataFrame({"date": y2025.date, "dow": y2025.dow, "day_type": y2025.day_type,
                          "day_off": y2025.is_day_off,
                          "holiday": y2025.holiday_name.replace("", None)})
    cal = pd.concat([y2025, calendar_2026()], ignore_index=True)
    cal = cal[(cal.date >= TIMELINE_START) & (cal.date <= TIMELINE_END)].reset_index(drop=True)
    cal["kind"] = cal.day_type.replace({"holiday": "sunday"})
    cal["source"] = cal.date.map(source_of)
    cal["date"] = cal.date.dt.strftime("%Y-%m-%d")
    return cal[["date", "dow", "day_type", "kind", "day_off", "holiday", "source"]]


def _minutes(clock: str) -> int:
    h, m = clock.split(":")
    return int(h) * 60 + int(m)


def service_hours() -> dict[int, set[int]]:
    """Часы суток, в которые маршрут возит пассажиров: окно работы с запасом, с переходом через полночь."""
    s = pd.read_csv(SCHEDULE)
    out: dict[int, set[int]] = {}
    for route, g in s.groupby("route"):
        first = min(_minutes(t) for t in g.service_from) - BEFORE_FIRST_MIN
        last = max(_minutes(t) + (24 * 60 if _minutes(t) < NEXT_DAY_BEFORE_MIN else 0) for t in g.service_to)
        last += AFTER_LAST_MIN
        hours = set()
        for h in range(HOURS):
            start, end = h * 60, h * 60 + 60
            # тот же день или хвост прошлого дня после полуночи
            if (start < last and end > first) or (start + 24 * 60 < last and end + 24 * 60 > first):
                hours.add(h)
        out[int(route)] = hours
    return out


def actuals_frame() -> tuple[pd.DataFrame, dict]:
    """Факт по часам без проверок оборудования и отчёт, сколько валидаций отброшено."""
    labels = load_labels()
    labels = labels[labels.date <= FACT_END]
    frame = pd.DataFrame({"route": labels.route, "date": labels.date.dt.strftime("%Y-%m-%d"), "hour": labels.hour,
                          "boardings": labels.boardings})
    hours = service_hours()
    off = np.array([h not in hours.get(r, set(range(HOURS))) for r, h in zip(frame.route, frame.hour)])
    dropped = frame[off & (frame.boardings > 0)]
    report = {
        "rule": "валидации вне часов работы маршрута - проверка оборудования, в факт идут нулём",
        "window": f"от первого отправления минус {BEFORE_FIRST_MIN} мин до последнего плюс {AFTER_LAST_MIN} мин "
                  "по расписанию transport.mos.ru",
        "cells": int(len(dropped)),
        "validations": int(dropped.boardings.sum()),
        "share_pct": round(100 * float(dropped.boardings.sum()) / float(frame.boardings.sum()), 4),
        "off_hours": {str(r): sorted(set(range(HOURS)) - h) for r, h in sorted(hours.items())},
    }
    return frame.assign(boardings=np.where(off, 0, frame.boardings)), report


def day_shapes(comp: pd.DataFrame, prediction: np.ndarray) -> tuple[pd.Series, pd.Series]:
    """Форма суток (доля часа) и вес типа дня к будню по маршрутам из прогноза декабря 2025."""
    fc = comp[["route", "date", "hour", "kind"]].assign(p=prediction)
    start = np.where(fc.route == 5, ROUTE5_SHAPE_FROM, SHAPE_FROM)
    fc = fc[(fc.date >= start) & (fc.date <= SHAPE_TO)]
    hourly = fc.groupby(["route", "kind", "hour"]).p.mean()
    daily = hourly.groupby(level=[0, 1]).sum()
    share = hourly / daily.reindex(hourly.index.droplevel(2)).to_numpy()
    weight = daily / daily.xs("workday", level=1).reindex(daily.index.get_level_values(0)).to_numpy()
    return share, weight


def day_weights(days: pd.DataFrame, route: int, weight: pd.Series, factors: OutlookFactors) -> np.ndarray:
    """Вес дня маршрута к среднему будню: тип дня × день недели × школьные каникулы × погода."""
    kind = days.kind.to_numpy()
    w = np.array([weight.get((route, k), 1.0) for k in kind])
    workday = kind == "workday"
    dow = days.dow.to_numpy()
    profile = factors.weekday.loc[route]
    w = w * np.where(workday, [profile.get(d, 1.0) for d in dow], 1.0)
    on_break = days.date.isin(factors.break_dates).to_numpy()
    w = w * np.where(workday & on_break, factors.school_break, 1.0)
    return w * days.date.map(factors.weather).fillna(1.0).to_numpy()


def outlook_frame(comp: pd.DataFrame, prediction: np.ndarray, year: pd.DataFrame, cal: pd.DataFrame,
                  factors: OutlookFactors) -> pd.DataFrame:
    """Оценка 2026 года по часам: сумма месяца из сезонного индекса, внутри месяца - поправки factors."""
    share, weight = day_shapes(comp, prediction)
    days = cal[cal.source == "outlook"].sort_values("date").reset_index(drop=True)
    month = days.date.str.slice(0, 7)
    parts = []
    for route in ROUTES:
        totals = year[(year.route == route) & (year.method == "seasonal_index")].set_index("month").p50
        daily = smooth_daily(days.date, day_weights(days, route, weight, factors), month.map(totals).to_numpy(float))
        for hour in range(HOURS):
            s = days.kind.map(lambda k, h=hour, r=route: share.get((r, k, h), 0.0)).to_numpy()
            parts.append(pd.DataFrame({"route": route, "date": days.date.to_numpy(), "hour": hour,
                                       "p50": np.round(daily * s, 1)}))
    out = pd.concat(parts, ignore_index=True)
    return out.sort_values(["route", "date", "hour"]).reset_index(drop=True)


def check(cal: pd.DataFrame, actuals: pd.DataFrame, outlook: pd.DataFrame, year: pd.DataFrame) -> None:
    days = (dt.date.fromisoformat(TIMELINE_END) - dt.date.fromisoformat(TIMELINE_START)).days + 1
    if len(cal) != days:
        raise ValueError(f"в календаре {len(cal)} дней вместо {days}")
    if len(actuals) != len(ROUTES) * 304 * HOURS:
        raise ValueError("факт января-октября 2025 неполный")
    sums = outlook.assign(month=outlook.date.str.slice(0, 7)).groupby(["route", "month"]).p50.sum()
    ref = year[year.method == "seasonal_index"].set_index(["route", "month"]).p50
    worst = float((sums.reindex(ref.index) / ref.replace(0, np.nan) - 1).abs().max())
    if worst > 0.002:
        raise ValueError(f"оценка 2026 не сходится с помесячным прогнозом: {worst:.2%}")
