"""Слой метро для карты: линии метро, МЦК и монорельса с цветами линий и станции из OpenStreetMap.

Трамвай в Москве часто подвозит к метро, поэтому диспетчеру нужна схема метро поверх карты.
Цвет линии берём из тега colour отношения, координаты округляем до 5 знаков (около 1 м)
и прореживаем точки ближе 15 м друг к другу: файл грузится фронтом лениво, при включении слоя.
Выход: external/osm_moscow_metro.geojson и его копия frontend/public/data/metro.geojson.
Запуск: uv run python analysis/s42_fetch_metro.py
"""

import json
import math

from common import ROOT
from s08_fetch_external import overpass

BBOX = "55.45,37.20,56.05,38.00"
MIN_STEP_M = 15.0
OUT = ROOT / "external" / "osm_moscow_metro.geojson"
FRONT = ROOT / "frontend" / "public" / "data" / "metro.geojson"
QUERY = f"""
[out:json][timeout:180];
(
  relation["type"="route"]["route"~"^(subway|light_rail|monorail)$"]({BBOX});
  relation["type"="route"]["route"="train"]["name"~"МЦК|центральное кольцо",i]({BBOX});
)->.lines;
.lines out geom;
node["railway"="station"]["station"~"^(subway|light_rail|monorail)$"]({BBOX});
out tags center;
node["railway"="station"]["network"~"МЦК"]({BBOX});
out tags center;
"""


def meters(a: list[float], b: list[float]) -> float:
    lat = math.radians((a[1] + b[1]) / 2)
    return math.hypot((a[0] - b[0]) * 111_320 * math.cos(lat), (a[1] - b[1]) * 110_540)


def thin(coords: list[list[float]]) -> list[list[float]]:
    out = [coords[0]]
    for c in coords[1:-1]:
        if meters(out[-1], c) >= MIN_STEP_M:
            out.append(c)
    out.append(coords[-1])
    return [[round(x, 5), round(y, 5)] for x, y in out]


def line_features(elements: list[dict]) -> list[dict]:
    """Одна линия - один MultiLineString: два направления одной линии рисуются одной фигурой."""
    lines: dict[str, dict] = {}
    for rel in (e for e in elements if e["type"] == "relation"):
        tags = rel.get("tags", {})
        name = tags.get("ref") or tags.get("name", "")
        key = f"{tags.get('route')}:{tags.get('colour', '')}:{name}"
        ways = [thin([[p["lon"], p["lat"]] for p in m["geometry"]]) for m in rel.get("members", [])
                if m["type"] == "way" and m.get("role", "") == "" and len(m.get("geometry", [])) >= 2]
        entry = lines.setdefault(key, {"ways": [], "tags": tags})
        entry["ways"] += [w for w in ways if w not in entry["ways"]]
    return [{"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": v["ways"]},
             "properties": {"kind": "line", "mode": v["tags"].get("route"), "ref": v["tags"].get("ref"),
                            "name": v["tags"].get("name"), "colour": v["tags"].get("colour", "#888888")}}
            for v in lines.values() if v["ways"]]


def station_features(elements: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for n in (e for e in elements if e["type"] == "node"):
        name = n.get("tags", {}).get("name")
        key = (name, round(n["lat"], 3), round(n["lon"], 3))
        if not name or key in seen:
            continue
        seen.add(key)
        out.append({"type": "Feature", "geometry": {"type": "Point",
                                                    "coordinates": [round(n["lon"], 5), round(n["lat"], 5)]},
                    "properties": {"kind": "station", "name": name, "mode": n["tags"].get("station"),
                                   "colour": n["tags"].get("colour")}})
    return out


def main() -> None:
    data = overpass(QUERY)
    elements = data.get("elements", [])
    geo = {"type": "FeatureCollection", "features": line_features(elements) + station_features(elements),
           "attribution": "© OpenStreetMap contributors, ODbL 1.0"}
    text = json.dumps(geo, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(text, encoding="utf-8")
    FRONT.parent.mkdir(parents=True, exist_ok=True)
    FRONT.write_text(text, encoding="utf-8")
    kinds = [f["properties"]["kind"] for f in geo["features"]]
    print(f"линий {kinds.count('line')}, станций {kinds.count('station')}, {len(text) / 1024:.0f} КБ")


if __name__ == "__main__":
    main()
