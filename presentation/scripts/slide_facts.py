"""Числа для презентации из артефактов и API сервиса: ничего не вписано руками.

Считает те же величины, что вкладка «Смена» (frontend/src/lib/dispatch.ts): посадки на рейс по расписанию
transport.mos.ru, узкие места, вагоны по обороту. Сбой из новостей переносится на другой день через API
сервиса, он должен быть запущен. Запуск из корня репозитория:
    uv run python presentation/scripts/slide_facts.py [http://localhost:8081]
"""

import json
import math
import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
OUT = ROOT / "presentation" / "src" / "data" / "facts.json"
CAPACITY = 185
QUIET = 15
SPEED_KMH = 17
LAYOVER_MIN = 5
MIN_HEADWAY = 3
MAX_QUIET_HEADWAY = 20
WEEK = pd.date_range("2025-11-15", "2025-11-21").strftime("%Y-%m-%d").tolist()
INCIDENT, TRY_ON = "24137", "2025-12-19"


def load():
    comp = pd.read_csv(ART / "forecast_components.csv", usecols=["route", "date", "hour", "prediction"])
    factors = json.loads((ART / "factors.json").read_text(encoding="utf-8"))
    day_off = {c["date"]: c["day_off"] for c in factors["calendar"]}
    net = json.loads((ART / "network.geojson").read_text(encoding="utf-8"))
    length = {}
    for f in net["features"]:
        p = f["properties"]
        if p.get("kind") == "path":
            length[p["route"]] = length.get(p["route"], 0) + p.get("length_m", 0)
    return comp, factors["schedule"]["routes"], day_off, length


def headway(schedule, route, off, hour):
    entry = schedule.get(str(route), {})
    table = (entry.get("weekend") or entry.get("weekday")) if off else entry.get("weekday")
    h = table["headway_min"][hour] if table else None
    return h if h and h > 0 else None


def need_headway(boardings: float) -> int:
    return math.floor(120 / math.ceil(boardings / CAPACITY))


def hourly(comp, schedule, day_off, cycle) -> pd.DataFrame:
    rows = []
    for r in comp.itertuples(index=False):
        hw = headway(schedule, r.route, day_off[r.date], r.hour)
        if not hw or r.prediction <= 0:
            continue
        per_trip = r.prediction / (2 * 60 / hw)
        now = math.ceil(cycle[r.route] / hw)
        extra = 0
        if per_trip > CAPACITY:
            extra = math.ceil(cycle[r.route] / max(MIN_HEADWAY, need_headway(r.prediction))) - now
        freed = 0
        if per_trip < QUIET and r.hour >= 6:
            quiet_hw = min(MAX_QUIET_HEADWAY, max(hw, math.floor(120 / max(math.ceil(r.prediction / QUIET), 1))))
            freed = now - math.ceil(cycle[r.route] / quiet_hw)
        rows.append(dict(route=r.route, date=r.date, hour=r.hour, b=r.prediction, hw=hw, per_trip=per_trip, veh=now,
                         extra=extra, freed=freed))
    return pd.DataFrame(rows)


def spans(d: pd.DataFrame) -> list[dict]:
    """Соседние часы выше вместимости склеиваются в отрезки «7-10 ч», как во вкладке «Смена»."""
    out = []
    over = d[d.per_trip > CAPACITY].sort_values(["route", "date", "hour"])
    for (route, date), g in over.groupby(["route", "date"]):
        start = prev = None
        best = None
        for r in g.itertuples():
            if prev is not None and r.hour != prev + 1:
                out.append(dict(route=route, date=date, start=start, end=prev + 1, **best))
                start, best = None, None
            if start is None:
                start = r.hour
            if best is None or r.per_trip > best["peak"]:
                best = dict(peak=round(r.per_trip), hour=r.hour, hw=r.hw, need=need_headway(r.b))
            prev = r.hour
        out.append(dict(route=route, date=date, start=start, end=prev + 1, **best))
    return sorted(out, key=lambda s: -s["peak"])


def top_stop(route: int, date: str, hour: int, comp: pd.DataFrame) -> str:
    stops = pd.read_csv(ART / "stops.csv", dtype={"stop_id": str}).set_index("stop_id")["name"]
    shares = pd.read_csv(ART / "route_stops.csv", dtype={"stop_id": str})
    own = shares[shares.route == route].groupby("stop_id").share.sum().sort_values(ascending=False)
    return str(stops[own.index[0]])


def api(base: str, path: str, body: dict | None = None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def incident(base: str) -> dict:
    feed = api(base, "/api/v1/news")
    item = next(i for i in feed["incidents"] if i["id"] == INCIDENT)
    events = api(base, f"/api/v1/news/{INCIDENT}/events?date={TRY_ON}")
    days = sorted({e["from"] for e in events})
    query = {"level": "network", "from": days[0], "to": days[-1], "granularity": "day"}
    result = api(base, "/api/v1/forecast/scenario", {"query": query, "coefficients": {}, "events": events})
    total = result["total"]
    return {"routes": item["routes"], "start": item["start"], "end": item["end"], "minutes": round(item["minutes"]),
            "cause": item["causeLabel"], "place": item["location"], "tryOn": TRY_ON, "events": len(events),
            "lost": round(total["baseline"] - total["p50"]), "alpha": feed["alpha"], "archive": len(feed["incidents"])}


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8081"
    comp, schedule, day_off, length = load()
    cycle = {r: length[r] / 1000 / SPEED_KMH * 60 + 2 * LAYOVER_MIN for r in length}
    d = hourly(comp, schedule, day_off, cycle)
    total_vh = int(d.veh.sum())
    over = d[d.per_trip > CAPACITY]
    r17 = d[(d.route == 17) & (d.date == "2025-11-14")].set_index("hour")
    week = spans(d[d.date.isin(WEEK)])
    facts = {
        "totalBoardings": round(comp.prediction.sum()),
        "route17": {"date": "2025-11-14", "hour": 8, "boardings": round(r17.loc[8].b), "headway": int(r17.loc[8].hw),
                    "perTrip": round(r17.loc[8].per_trip), "perTripByHour": [round(r17.per_trip.get(h, 0)) for h in range(24)],
                    "spans": [s for s in spans(d[(d.route == 17) & (d.date == "2025-11-14")])]},
        "week": {"from": WEEK[0], "to": WEEK[-1], "spans": len(week), "routes": len({s["route"] for s in week}),
                 "top": week[:3]},
        "overloadedHours": len(over), "overloadedPct": round(100 * len(over) / len(d), 1),
        "vehicleHours": total_vh, "extraVehicleHours": int(d.extra.sum()),
        "extraPct": round(100 * d.extra.sum() / total_vh, 1),
        "freedVehicleHours": int(d.freed.sum()),
        "overloadedByRoute": {str(k): int(v) for k, v in over.groupby("route").size().sort_values(ascending=False).items()},
        "topStop17": top_stop(17, "2025-11-14", 8, comp),
        "incident": incident(base),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(facts, ensure_ascii=False, indent=1, default=int), encoding="utf-8")
    print(json.dumps(facts, ensure_ascii=False, indent=1, default=int))


if __name__ == "__main__":
    main()
