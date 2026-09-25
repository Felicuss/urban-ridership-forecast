"""HTTP-клиент сервиса прогноза. Ошибки API (RFC 9457) превращаются в ToolError с текстом detail:
модель читает, что не так с запросом, и может переспросить пользователя."""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

DEFAULT_URL = "http://localhost:8080/api/v1"
TIMEOUT_S = 15.0


class TramApi:
    def __init__(self, base_url: str | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = (base_url or os.environ.get("TRAM_API_URL", DEFAULT_URL)).rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=TIMEOUT_S, transport=transport)

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._send("GET", path, params=_clean(params or {}))

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self._send("POST", path, json=body)

    def _send(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as e:
            raise ToolError(f"сервис прогноза недоступен ({self.base_url}): {e}") from e
        if response.status_code >= 400:
            raise ToolError(_problem(response))
        return response.json()


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None and v != ""}


def _problem(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"сервис ответил {response.status_code}"
    detail = body.get("detail") or body.get("title") or f"сервис ответил {response.status_code}"
    fields = [f"{e.get('field')}: {e.get('message')}" for e in body.get("errors", []) if e.get("field")]
    return detail if not fields or detail in fields else f"{detail} ({'; '.join(fields)})"
