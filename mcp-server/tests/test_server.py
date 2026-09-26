"""Важные проверки MCP-сервера: неверные параметры не доходят до API, ошибки API доходят до модели
понятным текстом, ряд прогноза сжимается без потери источника, команды интерфейсу проверяются."""

import json
from typing import Any

import anyio
import httpx
from mcp import Client
from mcp.types import TextContent

from tram_mcp import server
from tram_mcp.api import TramApi


def use_api(monkeypatch, handler) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(server, "API", TramApi("http://api.test/api/v1", transport=httpx.MockTransport(record)))
    return seen


def call(name: str, args: dict[str, Any]):
    async def run():
        async with Client(server.mcp) as client:
            return await client.call_tool(name, args)
    return anyio.run(run)


def text(result) -> str:
    return "".join(b.text for b in result.content if isinstance(b, TextContent))


def payload(result) -> Any:
    return json.loads(text(result))


def test_dates_outside_the_data_are_rejected_before_the_api(monkeypatch):
    seen = use_api(monkeypatch, lambda r: httpx.Response(200, json={}))

    result = call("forecast", {"level": "route", "id": "17", "date_from": "2027-01-01", "date_to": "2027-01-02"})

    assert result.is_error
    assert "2026-10-31" in text(result)
    assert seen == []


def test_forecast_is_summarised_with_peak_and_source(monkeypatch):
    points = [{"period": f"2025-11-14T{h:02d}:00", "p50": float(h), "p10": h - 1.0, "p90": h + 1.0,
               "source": "forecast"} for h in range(24)]
    series = {"target": {"name": "Маршрут 17"}, "granularity": "hour", "from": "2025-11-14", "to": "2025-11-14",
              "points": points, "total": {"p50": 276.0}}
    seen = use_api(monkeypatch, lambda r: httpx.Response(200, json=series))

    result = payload(call("forecast", {"level": "route", "id": "17", "horizon": "day", "date_from": "2025-11-14"}))

    assert seen[0].url.params["level"] == "route" and seen[0].url.params["id"] == "17"
    assert "to" not in seen[0].url.params
    assert result["peak"]["period"] == "2025-11-14T23:00"
    assert result["sources"] == ["forecast"]
    assert result["total"]["p50"] == 276.0


def test_api_problem_detail_reaches_the_model(monkeypatch):
    problem = {"title": "Запрос вне области определения модели", "status": 400,
               "detail": "id: остановки g0 нет в сети"}
    use_api(monkeypatch, lambda r: httpx.Response(400, json=problem))

    result = call("forecast", {"level": "stop", "id": "g0", "horizon": "day", "date_from": "2025-11-14"})

    assert result.is_error
    assert "остановки g0 нет в сети" in text(result)


def test_ui_commands_are_validated_actions_not_side_effects(monkeypatch):
    seen = use_api(monkeypatch, lambda r: httpx.Response(200, json={}))

    shown = payload(call("ui_show", {"date": "2025-12-31", "hour": 19, "route": 17, "view": "top"}))
    bad_route = call("ui_show", {"route": 3})
    bad_layer = call("ui_layers", {"enable": ["satellite", "radar"]})

    assert shown == {"ui": {"type": "show", "date": "2025-12-31", "hour": 19, "route": 17, "view": "top"}}
    assert bad_route.is_error and "маршрута 3 нет" in text(bad_route)
    assert bad_layer.is_error and "radar" in text(bad_layer)
    assert seen == []


def test_news_is_filtered_by_route_and_trimmed_for_the_model(monkeypatch):
    incident = {"id": "23459", "routes": [12], "start": "2025-11-08T10:28:51+03:00", "end": "2025-11-08T11:09:05+03:00",
                "minutes": 40.2, "cause": "technical_or_unspecified", "causeLabel": "технические причины",
                "location": "Авиамоторная", "sourceUrl": "https://t.me/DtOperativno/23459", "recoveryUrl": None,
                "inForecast": True, "origin": "archive", "events": [{"route": 12}]}
    other = {**incident, "id": "23678", "routes": [17]}
    use_api(monkeypatch, lambda r: httpx.Response(200, json={"incidents": [other, incident], "alpha": 0.5,
                                                              "liveCheckedAt": None, "liveError": None}))

    result = payload(call("transport_news", {"route": 12}))

    assert result["total"] == 1
    assert result["incidents"][0] == {
        "id": "23459", "routes": [12], "when": "08.11.2025 10:28 - 08.11.2025 11:09", "minutes": 40,
        "cause": "технические причины", "place": "Авиамоторная", "source": "https://t.me/DtOperativno/23459",
        "already_in_forecast": True, "origin": "archive"}


def test_news_events_come_back_in_scenario_format_and_bad_id_never_reaches_the_api(monkeypatch):
    seen = use_api(monkeypatch, lambda r: httpx.Response(200, json=[
        {"route": 12, "from": "2025-11-14", "to": "2025-11-14", "hours": "10-10", "multiplier": 0.74, "label": "сбой"}]))

    events = payload(call("news_events", {"incident_id": "23459", "date": "2025-11-14"}))["events"]
    bad = call("news_events", {"incident_id": "../meta", "date": "2025-11-14"})

    assert events == [{"route": 12, "date_from": "2025-11-14", "date_to": "2025-11-14", "hours": "10-10",
                       "multiplier": 0.74, "label": "сбой"}]
    assert bad.is_error
    assert len(seen) == 1 and seen[0].url.path == "/api/v1/news/23459/events"
