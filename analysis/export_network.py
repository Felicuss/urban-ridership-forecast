"""Остановки, доли посадок по остановкам и сеть GeoJSON для сервиса и карты.

Где взять порядок остановок: справочник организаторов покрывает маршруты 1, 5, 7, 11, 12
(лист «Порядок_с_координатами», основной вариант рейса в каждом направлении), для 17, 25, 26, 28
и 50 берём OpenStreetMap (external/osm_tram_routes.geojson, узлы с ролью stop по ходу рейса).
Остановку OSM, которая стоит ближе MATCH_METERS к остановке справочника, считаем той же, чтобы
общие остановки разных маршрутов складывались.

Доли. Остановки посадки в валидациях нет (place_id - площадка, а не остановка), поэтому доли -
оценка с сохранением суммы маршрута. Направления делят поток поровну. Внутри направления вес
падает по ходу рейса: w = (1 - x) + WEIGHT_FLOOR, x - доля пути по порядку остановок, конечная
получает 0 (там только выходят). WEIGHT_FLOOR = 0.29 даёт первым 10 % рейса 15.7 % посадок и
вес первой остановки 1.6 от среднего: по пачкам валидаций вагона первые 10 % времени полурейса
собирают 12.8-18.7 % посадок, вес начальной 1.6-3.2 (docs/research/review_round1.md, п. 7.3).
"""

import json

import numpy as np
import pandas as pd

from common import DATASET, ROOT
from typography import quotes

REFERENCE = DATASET / "spravochniki" / "tram_route_reference.xlsx"
OSM = ROOT / "external" / "osm_tram_routes.geojson"
REFERENCE_ROUTES = (1, 5, 7, 11, 12)
MATCH_METERS = 40.0
WEIGHT_FLOOR = 0.29
EARTH_RADIUS_M = 6_371_000.0


def reference_stops() -> pd.DataFrame:
    """Основной вариант рейса по направлениям из справочника: route, direction, seq, stop_id, name, lat, lon."""
    x = pd.read_excel(REFERENCE, sheet_name="Порядок_с_координатами")
    x = x[x.route_short_name.isin(REFERENCE_ROUTES)]
    main = x.groupby(["route_short_name", "direction_id"]).trip_id.transform(lambda t: t.value_counts().idxmax())
    x = x[x.trip_id == main].sort_values(["route_short_name", "direction_id", "stop_sequence"])
    return pd.DataFrame({
        "route": x.route_short_name.astype(int), "direction": x.direction_id.astype(int),
        "stop_id": "g" + x.stop_id.astype(int).astype(str), "name": x.stop_name,
        "lat": x.stop_lat.astype(float), "lon": x.stop_lon.astype(float), "source": "reference",
    }).reset_index(drop=True)


def all_reference_points() -> pd.DataFrame:
    """Все остановки справочника (10 маршрутов), к ним притягиваем остановки OSM."""
    x = pd.read_excel(REFERENCE, sheet_name="Порядок_с_координатами")
    x = x.drop_duplicates("stop_id")
    return pd.DataFrame({"stop_id": "g" + x.stop_id.astype(int).astype(str), "name": x.stop_name,
                         "lat": x.stop_lat.astype(float), "lon": x.stop_lon.astype(float)})


def osm_stops(geo: dict) -> pd.DataFrame:
    """Остановки OSM по ходу рейса. Направление - номер отношения маршрута по порядку id (0 и 1)."""
    rows = []
    for f in geo["features"]:
        p = f["properties"]
        route = int(p["route"])
        if p["kind"] != "stop" or not p["role"].startswith("stop") or route in REFERENCE_ROUTES:
            continue
        lon, lat = f["geometry"]["coordinates"]
        rows.append({"route": route, "rel": p["rel"], "stop_id": f"o{p['node']}", "name": p["name"],
                     "lat": lat, "lon": lon, "source": "osm"})
    df = pd.DataFrame(rows)
    df["direction"] = df.groupby("route").rel.rank(method="dense").astype(int) - 1
    return df.drop(columns="rel")


def haversine_m(lat1, lon1, lat2, lon2) -> np.ndarray:
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def match_to_reference(osm: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """Остановку OSM ближе MATCH_METERS к остановке справочника заменяем остановкой справочника."""
    d = haversine_m(osm.lat.to_numpy()[:, None], osm.lon.to_numpy()[:, None],
                    ref.lat.to_numpy()[None, :], ref.lon.to_numpy()[None, :])
    nearest = d.argmin(axis=1)
    hit = d[np.arange(len(osm)), nearest] <= MATCH_METERS
    out = osm.copy()
    matched = ref.iloc[nearest[hit]]
    out.loc[hit, ["stop_id", "name", "lat", "lon"]] = matched[["stop_id", "name", "lat", "lon"]].to_numpy()
    out.loc[hit, "source"] = "osm+reference"
    return out


def with_shares(route_stops: pd.DataFrame) -> pd.DataFrame:
    """Доля посадок маршрута на остановке: половина на направление, вес по ходу рейса, конечная 0."""
    parts = []
    for _, d in route_stops.groupby(["route", "direction"], sort=True):
        d = d.reset_index(drop=True)
        n = len(d)
        x = np.arange(n) / max(n - 1, 1)
        w = (1 - x) + WEIGHT_FLOOR
        w[-1] = 0.0
        parts.append(d.assign(seq=np.arange(1, n + 1), share=0.5 * w / w.sum()))
    return pd.concat(parts, ignore_index=True)


def relation_directions(geo: dict, ref: pd.DataFrame) -> dict[int, int]:
    """Номер направления для каждого отношения OSM, согласованный с остановками.

    У маршрутов справочника направление берём у справочника: чья первая остановка ближе к первой
    остановке отношения. У остальных - порядок id отношения, как в osm_stops.
    """
    first: dict[int, tuple[int, float, float]] = {}
    for f in geo["features"]:
        p = f["properties"]
        if p["kind"] == "stop" and p["role"].startswith("stop") and p["rel"] not in first:
            lon, lat = f["geometry"]["coordinates"]
            first[p["rel"]] = (int(p["route"]), lat, lon)
    out = {}
    for route in sorted({r for r, _, _ in first.values()}):
        rels = sorted(rel for rel, (r, _, _) in first.items() if r == route)
        starts = ref[ref.route == route].groupby("direction").first()
        for i, rel in enumerate(rels):
            if starts.empty:
                out[rel] = i
                continue
            _, lat, lon = first[rel]
            out[rel] = int(starts.index[haversine_m(lat, lon, starts.lat.to_numpy(), starts.lon.to_numpy()).argmin()])
    return out


def build_stops() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    geo = json.loads(OSM.read_text(encoding="utf-8"))
    ref = reference_stops()
    osm = match_to_reference(osm_stops(geo), all_reference_points())
    rs = with_shares(pd.concat([ref, osm], ignore_index=True))
    stops = (rs.groupby("stop_id").agg(name=("name", "first"), lat=("lat", "first"), lon=("lon", "first"),
                                       source=("source", "first"),
                                       routes=("route", lambda r: " ".join(map(str, sorted(set(r))))))
             .reset_index())
    stops["name"] = stops.name.map(quotes)
    route_stops = rs[["route", "direction", "seq", "stop_id", "share"]]
    stats = {"stops": int(len(stops)), "route_stop_rows": int(len(route_stops)),
             "osm_matched_to_reference": int((osm.source == "osm+reference").sum()), "osm_stops": int(len(osm))}
    return stops, route_stops, stats


def stitch(ways: list[list[list[float]]]) -> list[list[float]]:
    """Пути отношения OSM в одну линию по ходу рейса: каждый следующий путь разворачиваем к концу предыдущего.

    Члены отношения PTv2 идут по порядку движения, но направление каждого пути в OSM своё.
    Разрыв между путями (стрелки, развороты) остаётся прямым отрезком.
    """
    def gap(a, b):
        return haversine_m(a[1], a[0], b[1], b[0])

    first, rest = ways[0], ways[1:]
    if rest and min(gap(first[0], rest[0][0]), gap(first[0], rest[0][-1])) < min(
            gap(first[-1], rest[0][0]), gap(first[-1], rest[0][-1])):
        first = first[::-1]
    line = list(first)
    for way in rest:
        way = way if gap(line[-1], way[0]) <= gap(line[-1], way[-1]) else way[::-1]
        line += way[1:] if gap(line[-1], way[0]) < 1.0 else way
    return line


def route_paths(geo: dict, directions: dict[int, int]) -> list[dict]:
    """Непрерывная линия маршрута по направлению: по ней фронт ведёт трамвай и считает путь до остановок."""
    ways: dict[tuple[int, int], list] = {}
    for f in geo["features"]:
        p = f["properties"]
        if p["kind"] == "track":
            ways.setdefault((int(p["route"]), p["rel"]), []).append(f["geometry"]["coordinates"])
    features = []
    for (route, rel), members in sorted(ways.items()):
        line = [[round(x, 6), round(y, 6)] for x, y in stitch(members)]
        length = sum(haversine_m(a[1], a[0], b[1], b[0]) for a, b in zip(line, line[1:]))
        features.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": line},
                         "properties": {"kind": "path", "route": route, "direction": directions[rel],
                                        "osm_relation": rel, "length_m": round(float(length))}})
    return features


def network_geojson(stops: pd.DataFrame) -> dict:
    """Трассы маршрутов по направлениям (MultiLineString из путей OSM) и остановки с их маршрутами."""
    geo = json.loads(OSM.read_text(encoding="utf-8"))
    directions = relation_directions(geo, reference_stops())
    rels: dict[tuple[int, int], list] = {}
    for f in geo["features"]:
        p = f["properties"]
        if p["kind"] == "track":
            rels.setdefault((int(p["route"]), p["rel"]), []).append(
                [[round(x, 6), round(y, 6)] for x, y in f["geometry"]["coordinates"]])
    features = route_paths(geo, directions)
    for (route, rel), lines in sorted(rels.items()):
        features.append({"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": lines},
                         "properties": {"kind": "track", "route": route, "direction": directions[rel],
                                        "osm_relation": rel}})
    for s in stops.itertuples():
        features.append({"type": "Feature",
                         "geometry": {"type": "Point", "coordinates": [round(s.lon, 6), round(s.lat, 6)]},
                         "properties": {"kind": "stop", "stop_id": s.stop_id, "name": s.name,
                                        "routes": [int(r) for r in s.routes.split()], "source": s.source}})
    return {"type": "FeatureCollection", "features": features,
            "attribution": "© OpenStreetMap contributors, ODbL 1.0; справочник маршрутов и остановок"}
