"""Сбои из оперативных новостей Дептранса для сервиса: news.json.

Пары сообщений канала t.me/DtOperativno «задерживаются трамваи №…» и ответ «восстановлено движение
трамваев» собраны и проверены в analysis/s45_incident_adjustment.py (external/deptrans_incidents_2025.csv).
Время начала и конца - время публикации, а не телеметрия диспетчерской. Там же оценена доля посадок,
которую маршрут теряет за час полной остановки: сервис превращает сбой в события сценария по часам,
множитель часа равен 1 - alpha × доля часа под сбоем.
"""

import json

import pandas as pd

from common import ROOT, ROUTES

INCIDENTS = ROOT / "external" / "deptrans_incidents_2025.csv"
CALIBRATION = ROOT / "docs" / "analysis" / "tables" / "kaggle_incident_calibration.json"
CHANNEL = "https://t.me/s/DtOperativno"
CAUSES = {"contact_network", "road_accident", "blocked_tracks", "technical_or_unspecified"}


def build_news() -> dict:
    e = pd.read_csv(INCIDENTS, dtype={"event_id": str, "routes": str})
    cal = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    incidents = []
    for r in e.itertuples():
        routes = [int(x) for x in r.routes.split(";")]
        incidents.append({"id": r.event_id, "routes": routes, "start": r.start_ts, "end": r.end_ts, "cause": r.cause,
                          "location": r.location, "source_url": r.source_url, "recovery_url": r.recovery_url})
    news = {"channel": CHANNEL, "alpha": cal["raw_alpha"],
            "alpha_source": f"analysis/s45_incident_adjustment.py: {cal['historical_events']} сбоев января-октября "
                            f"2025 года, {cal['hour_cells']} часов под сбоем; с этой долей ошибка на часах сбоев "
                            f"меньше на {round(100 * cal['relative_error_reduction'])} %",
            "incidents": incidents}
    check(news)
    return news


def check(news: dict) -> None:
    if not 0 < news["alpha"] <= 1:
        raise ValueError(f"доля потерь за час сбоя вне (0, 1]: {news['alpha']}")
    for i in news["incidents"]:
        if not set(i["routes"]) <= set(ROUTES):
            raise ValueError(f"сбой {i['id']}: маршруты вне десяти целевых {i['routes']}")
        if i["cause"] not in CAUSES:
            raise ValueError(f"сбой {i['id']}: неизвестная причина {i['cause']}")
        if pd.Timestamp(i["end"]) <= pd.Timestamp(i["start"]):
            raise ValueError(f"сбой {i['id']}: конец раньше начала")
