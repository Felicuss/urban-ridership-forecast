"""Календарь 2025: праздники РФ, переносы, типы дней.

Праздники и переносы берём из пакета holidays (RU), он совпадает с
постановлением Правительства РФ о переносе выходных в 2025 году.
Рабочие субботы пакет не отдаёт, их задаём вручную.
"""

import datetime as dt

import holidays
import pandas as pd

YEAR = 2025
RU_HOLIDAYS = holidays.country_holidays("RU", years=YEAR)

# Суббота 1 ноября 2025 - рабочий день (перенос на понедельник 3 ноября).
WORKING_WEEKENDS = {dt.date(2025, 11, 1)}


def is_day_off(d: dt.date) -> bool:
    if d in WORKING_WEEKENDS:
        return False
    return d.weekday() >= 5 or d in RU_HOLIDAYS


def day_type(d: dt.date) -> str:
    """workday / saturday / sunday / holiday (нерабочий будний день)."""
    if d in WORKING_WEEKENDS:
        return "workday"
    if d in RU_HOLIDAYS and d.weekday() < 5:
        return "holiday"
    if d.weekday() == 5:
        return "saturday"
    if d.weekday() == 6:
        return "sunday"
    return "workday"


def calendar_frame(start: str, end: str) -> pd.DataFrame:
    days = pd.date_range(start, end, freq="D")
    rows = []
    for ts in days:
        d = ts.date()
        rows.append(
            {
                "date": ts,
                "dow": d.weekday(),
                "day_type": day_type(d),
                "is_day_off": is_day_off(d),
                "is_holiday": d in RU_HOLIDAYS,
                "holiday_name": RU_HOLIDAYS.get(d, ""),
            }
        )
    cal = pd.DataFrame(rows)
    off = cal["is_day_off"].to_numpy()
    # Предпраздничный / послепраздничный рабочий день: соседство с блоком выходных >= 3 дней
    # ловим отдельно в анализе, здесь только флаги соседства с выходным.
    cal["next_is_off"] = pd.Series(off).shift(-1, fill_value=False).to_numpy()
    cal["prev_is_off"] = pd.Series(off).shift(1, fill_value=False).to_numpy()
    return cal
