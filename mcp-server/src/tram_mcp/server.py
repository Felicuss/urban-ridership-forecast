"""MCP-сервер для агента диспетчера: данные сервиса прогноза и команды интерфейсу.

Инструменты данных ходят в REST API сервиса на Java. Команды интерфейсу (ui_*) ничего не меняют сами:
они проверяют параметры и возвращают действие {"ui": {...}}, которое агент передаёт фронту, а фронт
применяет к своему состоянию (дата, маршрут, вид карты, слои). Так модель не может сломать интерфейс
неверной датой или несуществующим маршрутом.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from tram_mcp.api import TramApi

TIMELINE_FROM = dt.date(2025, 1, 1)
TIMELINE_TO = dt.date(2026, 10, 31)
ROUTES = (1, 5, 7, 11, 12, 17, 25, 26, 28, 50)
MAX_POINTS = 400
MAX_CALENDAR_DAYS = 120
INCIDENT_ID = re.compile(r"^\d{1,12}$")
LAYERS = ("heat", "lines", "stops", "trams", "metro", "buildings", "weather", "daylight", "labels", "satellite")

Level = Literal["network", "route", "stop", "segment"]
Granularity = Literal["hour", "day", "month"]
Horizon = Literal["day", "month", "year"]

INSTRUCTIONS = """Ты помощник диспетчера трамвайной сети Москвы. Отвечаешь только про посадки на 10 трамвайных
маршрутах (1, 5, 7, 11, 12, 17, 25, 26, 28, 50) с 1 января 2025 по 31 октября 2026: январь-октябрь 2025 -
факт, ноябрь-декабрь 2025 - прогноз модели v6, 2026 год - оценка по сезонности. На другие темы вежливо
отказывай одной фразой. Числа бери только из инструментов, не придумывай; называй источник: факт, прогноз
или оценка. Если для запроса не хватает даты, маршрута или периода, спроси, чего не хватает, а не угадывай.
Чтобы показать что-то на экране, вызывай ui_show, ui_layers или ui_ride и передай их результат интерфейсу."""

mcp = MCPServer("tram-dispatcher", instructions=INSTRUCTIONS, version="0.1.0")
API = TramApi()


def _date(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    try:
        day = dt.date.fromisoformat(value)
    except ValueError as e:
        raise ToolError(f"{name}: дата пишется как ГГГГ-ММ-ДД, получено {value!r}") from e
    if not TIMELINE_FROM <= day <= TIMELINE_TO:
        raise ToolError(f"{name}: данные есть с {TIMELINE_FROM} по {TIMELINE_TO}, получено {value}")
    return value


def _route(route: int | None) -> int | None:
    if route is not None and route not in ROUTES:
        raise ToolError(f"маршрута {route} нет в сервисе, доступны {list(ROUTES)}")
    return route


def _summary(series: dict[str, Any]) -> dict[str, Any]:
    """Ряд прогноза без лишнего: итог, пик, источники и не больше MAX_POINTS точек."""
    points = series.get("points", [])
    peak = max(points, key=lambda p: p["p50"], default=None)
    return {
        "target": series.get("target", {}).get("name"),
        "granularity": series.get("granularity"),
        "period": [series.get("from"), series.get("to")],
        "unit": series.get("unit"),
        "total": series.get("total"),
        "peak": peak,
        "sources": sorted({p.get("source") for p in points if p.get("source")}),
        "points": points[:MAX_POINTS],
        "points_cut": max(len(points) - MAX_POINTS, 0),
        "notes": series.get("notes", []),
    }


@mcp.tool()
def model_info() -> dict[str, Any]:
    """Версия модели, точность на проверке организаторов, горизонт прогноза, границы данных и область применимости."""
    meta = API.get("/meta")
    keys = ("modelVersion", "leaderboardWapeScore", "horizonFrom", "horizonTo", "timelineFrom", "timelineTo",
            "routes", "applicability")
    return {k: meta.get(k) for k in keys}


@mcp.tool()
def list_routes() -> list[dict[str, Any]]:
    """Маршруты сервиса: номер, число остановок и прогноз посадок в среднем за сутки ноября-декабря 2025."""
    return API.get("/routes")


@mcp.tool()
def find_stops(query: str, route: int | None = None, limit: Annotated[int, Field(ge=1, le=50)] = 10) -> list[dict[str, Any]]:
    """Остановки по части названия, например «Сокол» или «Бауманская»; можно ограничить маршрутом."""
    _route(route)
    needle = query.strip().lower()
    stops = [s for s in API.get("/stops") if needle in s["name"].lower() and (route is None or route in s["routes"])]
    return [{"id": s["id"], "name": s["name"], "routes": s["routes"]} for s in stops[:limit]]


@mcp.tool()
def forecast(level: Level, id: str | None = None, date_from: str | None = None, date_to: str | None = None,
             granularity: Granularity | None = None, horizon: Horizon | None = None, hours: str | None = None,
             direction: int | None = None, from_stop: str | None = None, to_stop: str | None = None) -> dict[str, Any]:
    """Посадки по сети, маршруту (id - номер), остановке (id из find_stops) или участку (id - маршрут,
    direction 0/1, from_stop и to_stop). Период: date_from и date_to с шагом granularity, или horizon
    (day, month от date_from; year - ноябрь 2025 - октябрь 2026). hours - окно часов, например «7-10»."""
    if level == "route":
        _route(int(id) if id and id.isdigit() else None)
    query = {"level": level, "id": id, "from": _date(date_from, "date_from"), "to": _date(date_to, "date_to"),
             "granularity": granularity, "horizon": horizon, "hours": hours, "direction": direction,
             "fromStop": from_stop, "toStop": to_stop}
    return _summary(API.get("/forecast", query))


@mcp.tool()
def network_load(date: str, hour: Annotated[int, Field(ge=0, le=23)] | None = None) -> dict[str, Any]:
    """Посадки каждого маршрута за сутки и в выбранный час; пять самых загруженных остановок в этот час."""
    load = API.get("/network/load", {"date": _date(date, "date")})
    routes = {r["id"]: r["values"] for r in load.get("routes", [])}
    out: dict[str, Any] = {"date": load.get("date"), "source": load.get("source"),
                           "routes_day_total": {k: round(sum(v)) for k, v in routes.items()}}
    if hour is not None:
        out["routes_at_hour"] = {k: v[hour] for k, v in routes.items()}
        stops = sorted(load.get("stops", []), key=lambda s: -s["values"][hour])[:5]
        out["top_stops_at_hour"] = [{"id": s["id"], "boardings": round(s["values"][hour], 1)} for s in stops]
    return out


class Event(BaseModel):
    """Событие сценария: множитель посадок на маршруте (или всех) в дни и часы."""

    multiplier: float = Field(ge=0, le=5, description="0 - перекрытие, 1.3 - на 30 % больше")
    date_from: str
    date_to: str
    route: int | None = None
    hours: str | None = Field(default=None, description="окно часов, например 10-17")
    label: str | None = None


@mcp.tool()
def scenario(level: Level, id: str | None = None, date_from: str | None = None, date_to: str | None = None,
             granularity: Granularity | None = None, horizon: Horizon | None = None,
             coefficients: dict[str, float | str | bool] | None = None,
             events: list[Event] | None = None) -> dict[str, Any]:
    """Прогноз «что если»: ползунки (ключи из coefficients_catalog) и события (перекрытие, мероприятие,
    снегопад). Возвращает прогноз по сценарию, базу и разницу. Меняет только ноябрь-декабрь 2025."""
    query = {"level": level, "id": id, "from": _date(date_from, "date_from"), "to": _date(date_to, "date_to"),
             "granularity": granularity, "horizon": horizon}
    body = {"query": {k: v for k, v in query.items() if v is not None},
            "coefficients": coefficients or {},
            "events": [_event(e) for e in events or []]}
    result = API.post("/forecast/scenario", body)
    total = result.get("total", {})
    base = total.get("baseline") or 0
    value = total.get("p50", 0)
    # итог словами модели: сколько посадок со сценарием, без него и на сколько меньше или больше
    return {**_summary(result), "boardings_with_scenario": round(value), "boardings_default": round(base),
            "change_boardings": round(value - base),
            "delta_pct": round(100 * (value - base) / base, 2) if base else None}


def _event(e: Event) -> dict[str, Any]:
    _route(e.route)
    return {"multiplier": e.multiplier, "from": _date(e.date_from, "date_from"), "to": _date(e.date_to, "date_to"),
            "route": e.route, "hours": e.hours, "label": e.label}


@mcp.tool()
def coefficients_catalog() -> list[dict[str, Any]]:
    """Ползунки модели для scenario: ключ, подпись, значение по умолчанию, диапазон и источник."""
    keys = ("key", "label", "group", "type", "defaultValue", "min", "max", "step", "source")
    return [{k: c.get(k) for k in keys} for c in API.get("/coefficients")]


@mcp.tool()
def calendar(date_from: str, date_to: str) -> list[dict[str, Any]]:
    """Дни с типом (будни, выходной, праздник), названием праздника и источником данных (факт, прогноз, оценка)."""
    start, end = dt.date.fromisoformat(_date(date_from, "date_from")), dt.date.fromisoformat(_date(date_to, "date_to"))
    if (end - start).days > MAX_CALENDAR_DAYS:
        raise ToolError(f"за раз не больше {MAX_CALENDAR_DAYS} дней")
    return [d for d in API.get("/calendar") if date_from <= d["date"] <= date_to]


@mcp.tool()
def export_link(format: Literal["csv", "xlsx"], level: Level, date_from: str, date_to: str,
                granularity: Granularity = "hour", ids: list[str] | None = None, hours: str | None = None) -> dict[str, str]:
    """Ссылка на выгрузку прогноза в CSV или XLSX; пустой ids - все объекты уровня."""
    params = {"format": format, "level": level, "from": _date(date_from, "date_from"),
              "to": _date(date_to, "date_to"), "granularity": granularity, "hours": hours,
              "ids": ",".join(ids) if ids else None}
    query = "&".join(f"{k}={v}" for k, v in params.items() if v)
    public = os.environ.get("TRAM_PUBLIC_URL", API.base_url).rstrip("/")
    return {"url": f"{public}/export?{query}"}


@mcp.tool()
def transport_news(route: int | None = None, date_from: str | None = None, date_to: str | None = None,
                   limit: Annotated[int, Field(ge=1, le=40)] = 10) -> dict[str, Any]:
    """Сбои движения трамваев из оперативного канала Дептранса t.me/DtOperativno: проверенный архив 2025 года
    и свежие сообщения канала. У сбоя маршруты, начало и конец, причина, место, ссылка на сообщение и отметка,
    учтён ли он уже в прогнозе. Свежие сверху."""
    feed = API.get("/news")
    lo, hi = _date(date_from, "date_from"), _date(date_to, "date_to")
    items = [i for i in feed.get("incidents", [])
             if (route is None or _route(route) in i["routes"])
             and (lo is None or i["start"][:10] >= lo) and (hi is None or i["start"][:10] <= hi)]
    return {"alpha": feed.get("alpha"), "live_checked_at": feed.get("liveCheckedAt"), "live_error": feed.get("liveError"),
            "total": len(items), "incidents": [_incident(i) for i in items[:limit]]}


def _incident(i: dict[str, Any]) -> dict[str, Any]:
    """Сбой для модели: время уже по-русски и по Москве, чтобы модель не разбирала ISO со смещением сама."""
    start = dt.datetime.fromisoformat(i["start"])
    end = dt.datetime.fromisoformat(i["end"]) if i.get("end") else None
    when = f"{start:%d.%m.%Y %H:%M} - " + (f"{end:%d.%m.%Y %H:%M}" if end else "ещё не восстановлено")
    return {"id": i["id"], "routes": i["routes"], "when": when,
            "minutes": round(i["minutes"]) if i.get("minutes") is not None else None,
            "cause": i.get("causeLabel"), "place": i.get("location"), "source": i.get("sourceUrl"),
            "already_in_forecast": i.get("inForecast"), "origin": i.get("origin")}


@mcp.tool()
def news_events(incident_id: str, date: str) -> dict[str, list[dict[str, Any]]]:
    """События сценария, если такой же сбой случится в день date (1 ноября - 31 декабря 2025): те же часы и
    длительность. Результат передай в scenario как events, чтобы посчитать потерю посадок."""
    if not INCIDENT_ID.match(incident_id):
        raise ToolError("номер сбоя - число из transport_news, например 23459")
    events = API.get(f"/news/{incident_id}/events", {"date": _date(date, "date")})
    return {"events": [{"route": e.get("route"), "date_from": e["from"], "date_to": e["to"], "hours": e.get("hours"),
                        "multiplier": e["multiplier"], "label": e.get("label")} for e in events]}


@mcp.tool()
def ui_show(date: str | None = None, hour: Annotated[int, Field(ge=0, le=23)] | None = None, route: int | None = None,
            stop_id: str | None = None, view: Literal["top", "perspective"] | None = None,
            horizon: Horizon | None = None, tab: Literal["forecast", "shift", "scenario", "factors", "model"] | None = None,
            ) -> dict[str, Any]:
    """Команда интерфейсу: открыть дату и час, выбрать маршрут или остановку, вид карты, горизонт и вкладку.
    Вкладка shift - «Смена»: сводка смены, оповещения на завтра, узкие места недели, расчёт выпуска."""
    action = {"type": "show", "date": _date(date, "date"), "hour": hour, "route": _route(route), "stop": stop_id,
              "view": view, "horizon": horizon, "tab": tab}
    return {"ui": {k: v for k, v in action.items() if v is not None}}


@mcp.tool()
def ui_layers(enable: list[str] | None = None, disable: list[str] | None = None,
              hide_routes: list[int] | None = None) -> dict[str, Any]:
    """Команда интерфейсу: включить или выключить слои карты и скрыть маршруты. Слои: heat, lines, stops,
    trams, metro, buildings, weather, daylight, labels, satellite."""
    unknown = sorted((set(enable or []) | set(disable or [])) - set(LAYERS))
    if unknown:
        raise ToolError(f"нет слоёв {unknown}, есть {list(LAYERS)}")
    for r in hide_routes or []:
        _route(r)
    return {"ui": {"type": "layers", "enable": enable or [], "disable": disable or [],
                   **({"hideRoutes": hide_routes} if hide_routes is not None else {})}}


@mcp.tool()
def ui_ride(route: int, direction: Literal[0, 1] = 0) -> dict[str, Any]:
    """Команда интерфейсу: пустить трамвай маршрута по карте, камера едет за ним."""
    return {"ui": {"type": "ride", "route": _route(route), "direction": direction}}


def main() -> None:
    mcp.run(transport="streamable-http", host=os.environ.get("MCP_HOST", "127.0.0.1"),
            port=int(os.environ.get("MCP_PORT", "8765")), stateless_http=True, json_response=True)


if __name__ == "__main__":
    main()
