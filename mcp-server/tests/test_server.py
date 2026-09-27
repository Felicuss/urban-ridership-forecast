"""Важные проверки MCP-сервера: неверные параметры не доходят до API, ошибки API доходят до модели
понятным текстом, ряд прогноза сжимается без потери источника, команды интерфейсу проверяются."""

import datetime as dt
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

    result = call("forecast", {"level": "route", "id": "17", "date_from": "2028-01-01", "date_to": "2028-01-02"})

    assert result.is_error
    assert "2027-12-31" in text(result)
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


def test_client_logs_in_once_and_retries_when_the_session_is_missing():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, json={"username": "mcp"}, headers={"Set-Cookie": "chaspik_session=t0k; Path=/"})
        if "chaspik_session=t0k" not in request.headers.get("cookie", ""):
            return httpx.Response(401, json={"title": "Нужен вход", "detail": "сессии нет"})
        return httpx.Response(200, json={"ok": True})

    api = TramApi("http://api.test/api/v1", transport=httpx.MockTransport(handler), user="mcp", password="secret")

    assert api.get("/meta") == {"ok": True}
    assert api.get("/meta") == {"ok": True}
    assert [r.url.path for r in seen] == ["/api/v1/meta", "/api/v1/auth/login", "/api/v1/meta", "/api/v1/meta"]
    assert json.loads(seen[1].content) == {"username": "mcp", "password": "secret"}


def weekly_api(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/factors"):
        return httpx.Response(200, json={"schedule": {"routes": {
            str(r): {"weekday": {"headway_min": [10] * 24}, "weekend": {"headway_min": [20] * 24}}
            for r in server.ROUTES}}})
    if request.url.path.endswith("/calendar"):
        start = dt.date(2025, 1, 1)
        return httpx.Response(200, json=[{"date": (day := start + dt.timedelta(days=i)).isoformat(),
                                         "dayOff": day.weekday() >= 5} for i in range(365)])
    return httpx.Response(200, json={"source": "forecast", "routes": [
        {"id": r, "values": [1200 if r == 17 else 600] * 24} for r in server.ROUTES]})


def test_weekly_load_checks_all_routes_and_uses_weekend_intervals(monkeypatch):
    seen = use_api(monkeypatch, weekly_api)

    result = payload(call("weekly_load", {"date": "2025-11-16"}))

    assert result["period"] == ["2025-11-10", "2025-11-16"]
    assert result["days_checked"] == 7 and result["full_week"]
    assert result["routes_checked"] == list(server.ROUTES)
    assert len(result["routes"]) == 10
    assert result["risk_route_count"] == 1
    assert result["routes_at_risk"] == [17]
    peak = result["routes"][0]
    assert peak["route"] == 17
    assert peak["peak"] == {"date": "2025-11-15", "hour": 0, "boardings_per_trip": 200, "headway_min": 20}
    assert peak["hours_above_capacity"] == 48
    assert all(r["hours_above_capacity"] == 0 for r in result["routes"][1:])
    assert len([r for r in seen if r.url.path.endswith("/network/load")]) == 7
    # С запасом укладывается в лимит Java 6000 символов даже при форматированном JSON MCP.
    assert len(json.dumps(result, ensure_ascii=False, indent=2)) < 6000


def test_weekly_load_reports_partial_week_and_missing_schedule(monkeypatch):
    def handler(request):
        if request.url.path.endswith("/factors"):
            return httpx.Response(200, json={"schedule": {"routes": {}}})
        return weekly_api(request)
    use_api(monkeypatch, handler)

    result = payload(call("weekly_load", {"date": "2025-01-01", "route": 17}))

    assert result["requested_week"] == ["2024-12-30", "2025-01-05"]
    assert result["period"] == ["2025-01-01", "2025-01-05"]
    assert not result["full_week"]
    assert result["routes"][0]["hours_without_schedule"] == 120
    assert result["routes"][0]["peak"] is None


def test_weekly_load_rejects_invalid_route_before_api(monkeypatch):
    seen = use_api(monkeypatch, weekly_api)
    result = call("weekly_load", {"date": "2025-11-16", "route": 99})
    assert result.is_error
    assert not seen


def test_end_of_2027_is_forwarded_and_available_to_ui(monkeypatch):
    seen = use_api(monkeypatch, lambda r: httpx.Response(200, json={"points": [], "total": {"p50": 0}}))
    result = call("forecast", {"level": "network", "horizon": "year", "date_from": "2027-01-01"})
    assert not result.is_error
    assert seen[0].url.params["from"] == "2027-01-01"
    assert not call("ui_show", {"date": "2027-12-31"}).is_error


def test_day_network_total_and_peak_need_one_call(monkeypatch):
    use_api(monkeypatch, lambda r: httpx.Response(200, json={"date": "2027-10-04", "source": "outlook",
        "routes": [{"id": 1, "values": [5, 20] + [0] * 22}, {"id": 17, "values": [10, 30] + [0] * 22}]}))
    result = payload(call("network_load", {"date": "2027-10-04"}))
    assert result["network_day_total"] == 65
    assert result["network_peak"] == {"hour": 1, "boardings": 50}


def test_show_network_clears_route_and_stop():
    result = payload(call("ui_show", {"date": "2027-01-01", "network": True, "route": 17, "stop_id": "g2594", "horizon": "year"}))
    assert result["ui"] == {"type": "show", "date": "2027-01-01", "network": True, "horizon": "year"}
