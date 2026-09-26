"""Внешние факторы для интерфейса: всё, что объясняет прогноз и не входит в сами компоненты.

factors.json отдаёт сервис по GET /api/v1/factors. В нём календарь горизонта, почасовая
погода центра Москвы (Open-Meteo), загруженность дорог и городской пассажиропоток трамвая
(data.mos.ru), интервалы движения по часам (transport.mos.ru), посадки по дням за январь-октябрь
2025 (данные организаторов) и события сети. У каждого блока указан источник.
"""

import numpy as np
import pandas as pd

from calendar_ru import calendar_frame
from common import FORECAST_END, FORECAST_START, ROOT, ROUTES, load_labels
from typography import for_people

EXT = ROOT / "external"
HOURS = 24


def calendar_block() -> list[dict]:
    cal = calendar_frame(FORECAST_START, FORECAST_END)
    return [{"date": r.date.strftime("%Y-%m-%d"), "dow": int(r.dow), "day_type": r.day_type,
             "day_off": bool(r.is_day_off), "holiday": r.holiday_name or None} for r in cal.itertuples()]


def weather_block() -> dict:
    """Почасовая погода горизонта: массивы 61 × 24, пропуски как null."""
    w = pd.read_csv(EXT / "weather_moscow_2025_hourly.csv", parse_dates=["ts"])
    w = w[(w.ts >= FORECAST_START) & (w.ts < pd.Timestamp(FORECAST_END) + pd.Timedelta(days=1))]
    w = w.assign(date=w.ts.dt.strftime("%Y-%m-%d"), hour=w.ts.dt.hour)
    dates = sorted(w.date.unique())
    out = {"dates": dates, "source": "Open-Meteo Historical Weather API, центр Москвы 55.7558, 37.6173"}
    for col, key in (("temperature_2m", "temp"), ("precipitation", "precip"), ("snowfall", "snow"),
                     ("wind_speed_10m", "wind"), ("weather_code", "code"), ("cloud_cover", "cloud")):
        grid = w.pivot(index="date", columns="hour", values=col).reindex(index=dates, columns=range(HOURS))
        out[key] = [[None if pd.isna(v) else round(float(v), 1) for v in row] for row in grid.to_numpy()]
    return out


def traffic_block() -> dict:
    cong = pd.read_csv(EXT / "datamos_62525_monthly_congestion.csv")
    cong = cong[cong.year >= 2024]
    return {"source": "data.mos.ru, набор 62525: балл и процент загруженности дорог по месяцам",
            "months": [f"{int(r.year)}-{int(r.month):02d}" for r in cong.itertuples()],
            "score": [round(float(v), 2) for v in cong.congestion_score],
            "pct": [None if pd.isna(v) else round(float(v), 1) for v in cong.congestion_pct]}


def city_block() -> dict:
    city = pd.read_csv(EXT / "datamos_62521_monthly_ridership.csv")
    tram = city[city.transport == "Трамвай"].sort_values(["year", "month"])
    return {"source": "data.mos.ru, набор 62521: месячный пассажиропоток трамвая Москвы",
            "months": [f"{int(r.year)}-{int(r.month):02d}" for r in tram.itertuples()],
            "per_day": [round(float(v)) for v in tram.per_day]}


def schedule_block() -> dict:
    """Интервал в минутах по часам для будней и выходных; час вне работы маршрута - null."""
    s = pd.read_csv(EXT / "transport_mos_schedule.csv")
    out = {"source": "transport.mos.ru, расписание наземного транспорта", "fetched_at": s.fetched_at.iloc[0],
           "routes": {}}
    for route, g in s[s.direction == 0].groupby("route"):
        entry = {"title": for_people(g.title.iloc[0]), "page": g.page.iloc[0]}
        for day_type, d in g.groupby("day_type"):
            headway = [None] * HOURS
            for r in d.itertuples():
                h1, h2 = int(r.span_from[:2]), int(r.span_to[:2])
                for h in range(h1, h2 if h2 > h1 else h2 + HOURS):
                    headway[h % HOURS] = int(r.headway_min)
            entry[day_type] = {"headway_min": headway, "service_from": d.service_from.iloc[0],
                               "service_to": d.service_to.iloc[0]}
        out["routes"][str(int(route))] = entry
    return out


def history_block() -> dict:
    """Посадки по дням за январь-октябрь 2025: подложка графиков «история и прогноз»."""
    labels = load_labels()
    daily = labels.groupby(["route", "date"]).boardings.sum().unstack("route").reindex(columns=ROUTES, fill_value=0)
    return {"source": "данные организаторов, успешные валидации", "dates": [d.strftime("%Y-%m-%d") for d in daily.index],
            "routes": {str(r): [int(v) for v in daily[r].to_numpy()] for r in ROUTES}}


# Каталог событий ведётся для модели, и в нескольких строках там рабочие заметки. Диспетчеру
# показываем их итог; ключ - (start, routes).
EVENT_TEXT = {
    ("2025-11-12", "7;50"): {"effect": "оценка: 7 минус 5-15 %, в прогнозе по умолчанию не учтена"},
    ("2025-12-22", "all"): {"effect": "плюс несколько процентов"},
    ("2025-12-27", "50;12"): {"description": "депо им. Баумана закрыто на реконструкцию, 50 выпускается с площадки ТРЗ"},
}


def events_block() -> list[dict]:
    e = pd.read_csv(EXT / "events_2025.csv")
    e = e[e.end >= "2025-09-01"]
    out = []
    for r in e.itertuples():
        text = {"description": r.description, "effect": None if pd.isna(r.effect_in_data) else r.effect_in_data,
                **EVENT_TEXT.get((r.start, r.routes), {})}
        out.append({"start": r.start, "end": None if r.end.startswith("2099") else r.end, "routes": r.routes,
                    "days": r.days, "type": r.type, "description": for_people(text["description"]),
                    "source": r.source, "effect": text["effect"] and for_people(text["effect"])})
    return out


def build_factors() -> dict:
    return {"calendar": calendar_block(), "weather": weather_block(), "traffic": traffic_block(),
            "city_ridership": city_block(), "schedule": schedule_block(), "history": history_block(),
            "events": events_block()}


def check(factors: dict) -> None:
    w = factors["weather"]
    if len(w["dates"]) != 61 or np.array(w["temp"], dtype=float).shape != (61, HOURS):
        raise ValueError("погода горизонта неполная")
    if set(factors["schedule"]["routes"]) != {str(r) for r in ROUTES}:
        raise ValueError("в расписании нет части маршрутов")
