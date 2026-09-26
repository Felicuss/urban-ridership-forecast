"""Данные для макета интерфейса в презентации: то, что сервис показывает в пятницу 14 ноября 2025 в 8:10.

Прогноз с коридором, год, сравнение дат и сценарий сбоя берутся из API сервиса, остальное - из артефактов
теми же правилами, что во вкладке «Смена» (frontend/src/lib/dispatch.ts). Сервис должен быть запущен.
Запуск из корня репозитория:
    uv run python presentation/scripts/mock_data.py [http://localhost:8081]
"""

import json
import math
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
OUT = ROOT / "presentation" / "src" / "data" / "mock.json"
DAY, WEEK_AGO, TOMORROW = "2025-11-14", "2025-11-07", "2025-11-15"
WEEK = pd.date_range("2025-11-15", "2025-11-21").strftime("%Y-%m-%d").tolist()
CAPACITY, SPEED_KMH, LAYOVER = 185, 17, 5
INCIDENT, TRY_ON = "24137", "2025-12-19"
WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def api(base, path, body=None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def series(base, **query):
    s = api(base, "/api/v1/forecast?" + urllib.parse.urlencode(query))
    return [{"p50": round(p["p50"]), "p10": round(p["p10"]), "p90": round(p["p90"])} for p in s["points"]]


class Ctx:
    def __init__(self):
        self.comp = pd.read_csv(ART / "forecast_components.csv", usecols=["route", "date", "hour", "prediction"])
        self.factors = json.loads((ART / "factors.json").read_text(encoding="utf-8"))
        self.day_off = {c["date"]: c["day_off"] for c in self.factors["calendar"]}
        self.schedule = self.factors["schedule"]["routes"]
        self.stops = pd.read_csv(ART / "stops.csv", dtype={"stop_id": str}).set_index("stop_id")["name"]
        self.shares = pd.read_csv(ART / "route_stops.csv", dtype={"stop_id": str})
        net = json.loads((ART / "network.geojson").read_text(encoding="utf-8"))
        self.length = {}
        for f in net["features"]:
            p = f["properties"]
            if p.get("kind") == "path":
                self.length[p["route"]] = self.length.get(p["route"], 0) + p.get("length_m", 0)
        self.hours = {(r, d): g.sort_values("hour").prediction.tolist()
                      for (r, d), g in self.comp.groupby(["route", "date"])}

    def headway(self, route, date, hour):
        entry = self.schedule.get(str(route), {})
        table = (entry.get("weekend") or entry.get("weekday")) if self.day_off[date] else entry.get("weekday")
        h = table["headway_min"][hour] if table else None
        return h if h and h > 0 else None

    def per_trip(self, route, date):
        out = []
        for h, b in enumerate(self.hours[(route, date)]):
            hw = self.headway(route, date, h)
            out.append(b / (120 / hw) if hw else 0)
        return out

    def spans(self, route, date, merge_min=False):
        """Часы выше вместимости, склеенные в отрезки; совет - как в карточке «Посадок на рейс» или в «Смене»."""
        pt = self.per_trip(route, date)
        out = []
        for h, v in enumerate(pt):
            if v <= CAPACITY:
                continue
            b = self.hours[(route, date)][h]
            need = math.floor(120 / math.ceil(b / CAPACITY))
            hw = self.headway(route, date, h)
            if out and out[-1]["end"] == h:
                s = out[-1]
                s["end"] = h + 1
                s["hwMin"] = min(s["hwMin"], hw)
                s["needMin"] = min(s["needMin"], need)
                if v > s["peak"]:
                    s.update(peak=round(v), hour=h, hw=hw, need=need)
            else:
                out.append({"route": route, "date": date, "start": h, "end": h + 1, "peak": round(v), "hour": h, "hw": hw,
                            "need": need, "hwMin": hw, "needMin": need})
        return out

    def top_stop(self, route, date, hour):
        own = self.shares[self.shares.route == route]
        v = own.assign(v=own.share * self.hours[(route, date)][hour]).groupby("stop_id").v.sum()
        return str(self.stops[v.idxmax()])

    def cycle(self, route):
        return self.length[route] / 1000 / SPEED_KMH * 60 + 2 * LAYOVER


def weather(c):
    w = c.factors["weather"]
    i = w["dates"].index(DAY)
    temps = w["temp"][i]
    wet = [(w["precip"][i][h] or 0) for h in range(24)]
    hours = [h for h, v in enumerate(wet) if v >= 0.1]
    line = f"+{round(min(temps))}°…+{round(max(temps))}°"
    line += f", дождь {hours[0]}-{hours[-1] + 1} ч, {sum(wet):.1f} мм".replace(".", ",") if hours else ", без осадков"
    return {"temp": temps, "precip": wet, "code": w["code"][i], "line": line}


def events(c):
    out = []
    for e in c.factors["events"]:
        active = e["start"] <= DAY <= (e["end"] or e["start"]) if e["end"] else e["start"] == DAY
        days_ok = e["days"] == "all" or (e["days"] == "weekends") == c.day_off[DAY]
        if active and days_ok and e["type"] != "data_anomaly":
            out.append(e["description"] if e["routes"] == "all" else f"{e['routes'].replace(';', ', ')}: {e['description']}")
    return out


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8081"
    c = Ctx()
    routes = sorted({r for r, _ in c.hours})
    net_day = [sum(c.hours[(r, DAY)][h] for r in routes) for h in range(24)]
    net_week = sum(sum(c.hours[(r, WEEK_AGO)]) for r in routes)
    dates = sorted({d for _, d in c.hours})
    matrix = [[round(sum(c.hours[(r, d)][h] for r in routes)) for h in range(24)] for d in dates]

    r17 = c.shares[(c.shares.route == 17) & (c.shares.direction == 0)].sort_values("seq")
    b8 = c.hours[(17, DAY)][8]
    stops17 = [{"seq": int(s.seq), "name": str(c.stops[s.stop_id]), "value": round(s.share * b8)} for s in r17.itertuples()]
    last = lambda d: str(c.stops[c.shares[(c.shares.route == 17) & (c.shares.direction == d)].sort_values("seq").stop_id.iloc[-1]])

    crowded = sorted([s for r in routes for s in c.spans(r, DAY)], key=lambda s: -s["peak"])[:4]
    week = sorted([s for d in WEEK for r in routes for s in c.spans(r, d)], key=lambda s: -s["peak"])
    for s in week[:6]:
        s["stop"] = c.top_stop(s["route"], s["date"], s["hour"])
        d = pd.Timestamp(s["date"])
        s["label"] = f"{WEEKDAYS[d.dayofweek]} {d.day:02d}.{d.month:02d}"

    cyc = c.cycle(17)
    fleet_hours = [7, 8, 9]
    fleet = {"cycle": round(cyc), "lengthKm": round(c.length[17] / 1000, 1),
             "byHeadway": {hw: {"vehicles": math.ceil(cyc / hw),
                                "perTrip": round(max(c.hours[(17, DAY)][h] for h in fleet_hours) / (120 / hw)),
                                "vehicleHours": math.ceil(cyc / hw) * len(fleet_hours)} for hw in range(3, 13)},
             "scheduleHeadway": min(c.headway(17, DAY, h) for h in fleet_hours),
             "scheduleVehicles": max(math.ceil(cyc / c.headway(17, DAY, h)) for h in fleet_hours),
             "scheduleVehicleHours": sum(math.ceil(cyc / c.headway(17, DAY, h)) for h in fleet_hours)}

    feed = api(base, "/api/v1/news")
    news = [{k: i[k] for k in ("id", "routes", "start", "end", "minutes", "causeLabel", "location", "inForecast")}
            for i in feed["incidents"][:5]]
    ev = api(base, f"/api/v1/news/{INCIDENT}/events?date={TRY_ON}")
    horizon = {"level": "network", "from": "2025-11-01", "to": "2025-12-31", "granularity": "day"}
    sc = api(base, "/api/v1/forecast/scenario", {"query": horizon, "coefficients": {}, "events": ev})
    scenario = {"events": ev, "total": round(sc["total"]["p50"]), "baseline": round(sc["total"]["baseline"]),
                "deltas": [round(p["p50"] - p["baseline"]) for p in sc["points"]]}
    day19 = api(base, "/api/v1/forecast/scenario", {"query": {"level": "route", "id": "17", "horizon": "day", "from": TRY_ON},
                                                    "coefficients": {}, "events": ev})
    scenario["route17"] = [{"p50": round(p["p50"]), "base": round(p["baseline"])} for p in day19["points"]]

    board = []
    for r in routes:
        hw = c.headway(r, DAY, 8)
        h = c.hours[(r, DAY)]
        board.append({"route": r, "now": round(h[8]), "next": round(h[9]), "headway": hw,
                      "perTrip": round(h[8] / (120 / hw)) if hw and h[8] > 0 else None})

    mock = {
        "date": DAY, "dateLabel": "14 ноября 2025, пятница", "weather": weather(c),
        "network": {"day": series(base, level="network", horizon="day", **{"from": DAY}),
                    "year": series(base, level="network", horizon="year"), "matrix": matrix, "matrixFrom": dates[0]},
        "routes": [{"route": r, "title": c.schedule[str(r)]["title"], "total": round(sum(c.hours[(r, DAY)])),
                    "hours": [round(v) for v in c.hours[(r, DAY)]]} for r in routes],
        "route17": {"day": series(base, level="route", id="17", horizon="day", **{"from": DAY}),
                    "compare": series(base, level="route", id="17", horizon="day", **{"from": WEEK_AGO}),
                    "perTrip": [round(v) for v in c.per_trip(17, DAY)], "spans": c.spans(17, DAY),
                    "headway8": c.headway(17, DAY, 8), "stops": stops17, "ends": [last(0), last(1)]},
        "brief": {"total": round(sum(net_day)), "peakHour": net_day.index(max(net_day)), "peak": round(max(net_day)),
                  "vsWeek": round(100 * (sum(net_day) - net_week) / net_week, 1),
                  "top": sorted([{"route": r, "total": round(sum(c.hours[(r, DAY)]))} for r in routes], key=lambda x: -x["total"])[:3],
                  "crowded": crowded, "events": events(c)},
        "alert": {"date": TOMORROW, "spans": c.spans(17, TOMORROW)},
        "week": {"count": len(week), "routes": len({s["route"] for s in week}), "top": week[:6]},
        "fleet": fleet,
        "news": {"incidents": news, "alpha": feed["alpha"], "tryOn": TRY_ON, "incident": INCIDENT, "scenario": scenario},
        "board": board,
    }
    OUT.write_text(json.dumps(mock, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"mock.json {OUT.stat().st_size / 1024:.0f} КБ; сводка {mock['brief']['total']}, узких мест {len(week)}, "
          f"сценарий {scenario['total'] - scenario['baseline']}")


if __name__ == "__main__":
    main()
