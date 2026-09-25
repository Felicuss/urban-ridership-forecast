"""Шкала времени интерфейса: 01.01.2025 - 31.10.2026, чтобы смотреть любую дату, а не только горизонт.

- январь-октябрь 2025 - факт: успешные валидации по часам из данных организаторов;
- ноябрь-декабрь 2025 - почасовой прогноз модели (forecast_components.csv, пересчитывается сценарием);
- январь-октябрь 2026 - оценка: месячный прогноз года (forecast_year.csv) раскладывается по дням с весом
  типа дня и по часам с формой суток маршрута из прогноза декабря 2025 (1-28.12, без предновогодних дней).

Календарь 2025 - как в модели (calendar_ru, рабочая суббота 01.11), 2026 - официальный производственный
календарь isdayoff.ru с переносами (09.01, 09.03, 11.05 и др.), названия праздников из пакета holidays.
"""

import datetime as dt

import holidays
import numpy as np
import pandas as pd

from calendar_ru import calendar_frame
from common import ROOT, ROUTES, load_labels

TIMELINE_START, TIMELINE_END = "2025-01-01", "2026-10-31"
FACT_END, FORECAST_END = "2025-10-31", "2025-12-31"
SHAPE_FROM, SHAPE_TO = "2025-12-01", "2025-12-28"
ROUTE5_SHAPE_FROM = "2025-12-17"
HOURS = 24


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


def actuals_frame() -> pd.DataFrame:
    labels = load_labels()
    labels = labels[labels.date <= FACT_END]
    return pd.DataFrame({"route": labels.route, "date": labels.date.dt.strftime("%Y-%m-%d"), "hour": labels.hour,
                         "boardings": labels.boardings})


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


def outlook_frame(comp: pd.DataFrame, prediction: np.ndarray, year: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    share, weight = day_shapes(comp, prediction)
    days = cal[cal.source == "outlook"].assign(month=lambda c: c.date.str.slice(0, 7))
    parts = []
    for route in ROUTES:
        totals = year[(year.route == route) & (year.method == "seasonal_index")].set_index("month").p50
        w = days.kind.map(lambda k: weight.get((route, k), 1.0)).to_numpy()
        month_w = pd.Series(w).groupby(days.month.to_numpy()).transform("sum").to_numpy()
        daily = days.month.map(totals).to_numpy() * w / month_w
        for hour in range(HOURS):
            s = days.kind.map(lambda k, h=hour: share.get((route, k, h), 0.0)).to_numpy()
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
