"""Слой метро для карты: линии метро, МЦК и монорельса с цветами линий и станции из OpenStreetMap.

Трамвай в Москве часто подвозит к метро, поэтому диспетчеру нужна схема метро поверх карты.
Цвет линии берём из тега colour отношения, координаты округляем до 5 знаков (около 1 м)
и прореживаем точки ближе 15 м друг к другу: файл грузится фронтом лениво, при включении слоя.
МЦК ищем по ref=14 и сети метрополитена: регулярное выражение Overpass с флагом i не приводит
регистр кириллицы, и поиск по имени её пропускал. Станции МЦК - остановки из того же отношения.
Выход: external/osm_moscow_metro.geojson и его копия frontend/public/data/metro.geojson.
Запуск: uv run python analysis/s42_fetch_metro.py
       uv run python analysis/s42_fetch_metro.py --mcc   # только МЦК, если общий запрос отвечает 504
"""

import json
import math
import sys

from common import ROOT
from s08_fetch_external import overpass

BBOX = "55.45,37.20,56.05,38.00"
MIN_STEP_M = 15.0
SAME_STATION_M = 300.0
MCC = '["type"="route"]["route"="train"]["ref"="14"]["network"="Московский метрополитен"]'
NAMED_COLOURS = {"red": "#EF161E"}
OUT = ROOT / "external" / "osm_moscow_metro.geojson"
FRONT = ROOT / "frontend" / "public" / "data" / "metro.geojson"
METRO_QUERY = f"""
[out:json][timeout:180];
relation["type"="route"]["route"~"^(subway|light_rail|monorail)$"]({BBOX});
out geom;
node["railway"="station"]["station"~"^(subway|light_rail|monorail)$"]({BBOX});
out tags center;
"""
MCC_QUERY = f"""
[out:json][timeout:120];
relation{MCC}({BBOX})->.mcc;
.mcc out geom;
node(r.mcc:"stop");
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
                            "name": v["tags"].get("name"),
                            "colour": colour(v["tags"].get("colour", "#888888"))}}
            for v in lines.values() if v["ways"]]


def colour(value: str) -> str:
    return NAMED_COLOURS.get(value, value)


def station_features(elements: list[dict]) -> list[dict]:
    """Станция одна на имя в радиусе 300 м: у МЦК остановки двух направлений стоят рядом."""
    out: list[dict] = []
    # у части остановок имя маршрута вместо имени станции: такие узлы не станции
    routes = {e.get("tags", {}).get("name") for e in elements if e["type"] == "relation"}
    for n in (e for e in elements if e["type"] == "node"):
        tags = n.get("tags", {})
        name = tags.get("name")
        at = [round(n["lon"], 5), round(n["lat"], 5)]
        if not name or name in routes or any(f["properties"]["name"] == name and meters(f["geometry"]["coordinates"], at) < SAME_STATION_M
                           for f in out):
            continue
        mode = tags.get("station") or ("train" if tags.get("railway") in ("stop", "station", "halt")
                                       or tags.get("train") == "yes" else None)
        out.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": at},
                    "properties": {"kind": "station", "name": name, "mode": mode, "colour": tags.get("colour")}})
    return out


def is_mcc(feature: dict) -> bool:
    props = feature["properties"]
    return props.get("mode") == "train" or (props["kind"] == "line" and props.get("ref") == "14")


def main() -> None:
    mcc = overpass(MCC_QUERY).get("elements", [])
    if "--mcc" in sys.argv:
        old = json.loads(OUT.read_text(encoding="utf-8"))["features"]
        metro_lines = [f for f in old if f["properties"]["kind"] == "line" and not is_mcc(f)]
        metro_stations = [f for f in old if f["properties"]["kind"] == "station" and not is_mcc(f)]
    else:
        metro = overpass(METRO_QUERY).get("elements", [])
        metro_lines, metro_stations = line_features(metro), station_features(metro)
    features = metro_lines + line_features(mcc) + metro_stations + station_features(mcc)
    geo = {"type": "FeatureCollection", "features": features,
           "attribution": "© OpenStreetMap contributors, ODbL 1.0"}
    text = json.dumps(geo, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(text, encoding="utf-8")
    FRONT.parent.mkdir(parents=True, exist_ok=True)
    FRONT.write_text(text, encoding="utf-8")
    kinds = [f["properties"]["kind"] for f in geo["features"]]
    print(f"линий {kinds.count('line')}, станций {kinds.count('station')}, {len(text) / 1024:.0f} КБ")


if __name__ == "__main__":
    main()
