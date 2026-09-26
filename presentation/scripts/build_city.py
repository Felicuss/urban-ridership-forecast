"""Карта Москвы для презентации: трамвайные линии, остановки с посадками по часам, метро, МКАД, река, дороги.

Всё переводится в метры от центра (37.62, 55.755) и упрощается по Дугласу-Пекеру, чтобы презентация
осталась одним лёгким HTML и рисовала город на canvas без тайлов и без сети. Запуск из корня репозитория:
    uv run python presentation/scripts/build_city.py
Дороги, МКАД и река скачиваются из OpenStreetMap через Overpass один раз и кэшируются в data/.
"""

import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis"))
from s08_fetch_external import overpass  # noqa: E402

ART = ROOT / "artifacts"
EXT = ROOT / "external"
CACHE = ROOT / "data" / "presentation_osm.json"
OUT = ROOT / "presentation" / "src" / "data" / "city.json"
LON0, LAT0 = 37.62, 55.755
KX = 111_320 * math.cos(math.radians(LAT0))
KY = 110_540
DAY = "2025-11-14"
BBOX = "55.54,37.33,55.96,37.90"

OSM_QUERY = f"""
[out:json][timeout:180];
(
  way["highway"~"^(motorway|trunk|primary)$"]({BBOX});
  way["waterway"="river"]["name"="Москва"]({BBOX});
  way["waterway"="river"]["name"="Яуза"]({BBOX});
);
out geom;
"""


def xy(lon: float, lat: float) -> tuple[float, float]:
    return (lon - LON0) * KX, (lat - LAT0) * KY


def rdp(points: list[tuple[float, float]], eps: float) -> list[tuple[float, float]]:
    """Упрощение линии: точки, отстоящие от хорды меньше eps метров, отбрасываются."""
    if len(points) < 3:
        return points
    (ax, ay), (bx, by) = points[0], points[-1]
    dx, dy = bx - ax, by - ay
    norm = math.hypot(dx, dy) or 1e-9
    far, index = 0.0, 0
    for i, (px, py) in enumerate(points[1:-1], start=1):
        d = abs(dy * px - dx * py + bx * ay - by * ax) / norm
        if d > far:
            far, index = d, i
    if far <= eps:
        return [points[0], points[-1]]
    return rdp(points[: index + 1], eps)[:-1] + rdp(points[index:], eps)


def flat(coords, eps: float) -> list[int]:
    pts = rdp([xy(lon, lat) for lon, lat in coords], eps)
    return [round(v) for p in pts for v in p]


def osm() -> dict:
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(overpass(OSM_QUERY), ensure_ascii=False), encoding="utf-8")
    return json.loads(CACHE.read_text(encoding="utf-8"))


def city_layers() -> dict:
    roads, mkad, river = [], [], []
    for el in osm().get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        tags = el.get("tags", {})
        coords = [(g["lon"], g["lat"]) for g in el["geometry"]]
        if tags.get("waterway") == "river":
            river.append(flat(coords, 20))
        elif tags.get("ref") == "МКАД" or "МКАД" in tags.get("name", ""):
            mkad.append(flat(coords, 30))
        else:
            kind = 0 if tags["highway"] in ("motorway", "trunk") else 1
            line = flat(coords, 25)
            if len(line) >= 4:
                roads.append([kind, *line])
    return {"roads": roads, "mkad": mkad, "river": river}


def metro() -> list[dict]:
    g = json.loads((EXT / "osm_moscow_metro.geojson").read_text(encoding="utf-8"))
    lines = []
    for f in g["features"]:
        if f["geometry"]["type"] != "MultiLineString":
            continue
        for part in f["geometry"]["coordinates"]:
            line = flat(part, 30)
            if len(line) >= 4:
                lines.append({"c": f["properties"].get("colour") or "#888888", "p": line})
    return lines


def network() -> tuple[list[dict], list[dict], dict]:
    g = json.loads((ART / "network.geojson").read_text(encoding="utf-8"))
    comp = pd.read_csv(ART / "forecast_components.csv", usecols=["route", "date", "hour", "prediction"])
    day = comp[comp.date == DAY].pivot(index="route", columns="hour", values="prediction").fillna(0)
    shares = pd.read_csv(ART / "route_stops.csv", dtype={"stop_id": str})
    by_stop: dict[str, list[float]] = {}
    for r in shares.itertuples():
        hours = day.loc[r.route].to_numpy() * r.share
        acc = by_stop.setdefault(r.stop_id, [0.0] * 24)
        for h in range(24):
            acc[h] += hours[h]
    paths, stops = [], []
    for f in g["features"]:
        p = f["properties"]
        if p.get("kind") == "path":
            paths.append({"r": p["route"], "d": p["direction"], "p": flat(f["geometry"]["coordinates"], 6)})
        elif p.get("kind") == "stop" and p.get("stop_id") in by_stop:
            x, y = xy(*f["geometry"]["coordinates"])
            stops.append({"id": p["stop_id"], "n": p.get("name", ""), "x": round(x), "y": round(y),
                          "r": p.get("routes", []), "h": [round(v) for v in by_stop[p["stop_id"]]]})
    routes = {str(r): [round(v) for v in day.loc[r].to_numpy()] for r in day.index}
    return paths, stops, routes


def main() -> None:
    paths, stops, routes = network()
    city = {"day": DAY, "center": [LON0, LAT0], "trams": paths, "stops": stops, "routeHours": routes,
            "metro": metro(), **city_layers()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(city, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size = OUT.stat().st_size / 1024
    print(f"city.json {size:.0f} КБ: {len(paths)} трасс, {len(stops)} остановок, {len(city['metro'])} линий метро, "
          f"{len(city['roads'])} дорог, МКАД {len(city['mkad'])}, река {len(city['river'])}")


if __name__ == "__main__":
    main()
