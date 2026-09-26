"""Проверка живого MCP-сервера по сети: список инструментов и несколько вызовов.

uv run python scripts/smoke.py http://127.0.0.1:8765/mcp
"""

import sys

import anyio
from mcp import Client
from mcp.types import TextContent

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/mcp"
CALLS = [
    ("model_info", {}),
    ("find_stops", {"query": "Сокол", "limit": 3}),
    ("forecast", {"level": "route", "id": "17", "horizon": "day", "date_from": "2025-11-14"}),
    ("network_load", {"date": "2025-11-14", "hour": 8}),
    ("forecast", {"level": "route", "id": "99", "horizon": "day", "date_from": "2025-11-14"}),
    ("ui_show", {"date": "2025-11-14", "hour": 8, "route": 17}),
]


async def main() -> None:
    async with Client(URL) as client:
        tools = await client.list_tools()
        print("tools:", ", ".join(t.name for t in tools.tools))
        for name, args in CALLS:
            result = await client.call_tool(name, args)
            body = "".join(b.text for b in result.content if isinstance(b, TextContent))
            print(f"{name}: error={result.is_error} {body[:220]}")


anyio.run(main)
