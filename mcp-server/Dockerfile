# MCP-сервер агента: Python 3.14, зависимости по uv.lock, транспорт Streamable HTTP на 8765.
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev
ENV MCP_HOST=0.0.0.0 MCP_PORT=8765 TRAM_API_URL=http://api:8080/api/v1
EXPOSE 8765
USER nobody
CMD ["/app/.venv/bin/tram-mcp"]
