package ru.mojarung.tramload.infrastructure.agent;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

import ru.mojarung.tramload.domain.agent.AgentFailure;
import ru.mojarung.tramload.domain.agent.AgentTools;
import ru.mojarung.tramload.domain.agent.ToolResult;
import ru.mojarung.tramload.domain.agent.ToolSpec;

/**
 * Инструменты агента с MCP-сервера (mcp-server/) по Streamable HTTP. Сервер работает без сессий и отвечает
 * JSON, поэтому каждый вызов - один POST JSON-RPC: tools/list и tools/call, без рукопожатия.
 */
final class McpHttpTools implements AgentTools {

	private static final String PROTOCOL = "2025-06-18";

	private final HttpClient http;
	private final JsonMapper json;
	private final URI endpoint;
	private final Duration timeout;
	private final AtomicLong ids = new AtomicLong();
	private volatile List<ToolSpec> specs;

	McpHttpTools(HttpClient http, JsonMapper json, String url, Duration timeout) {
		this.http = http;
		this.json = json;
		this.endpoint = URI.create(url);
		this.timeout = timeout;
	}

	/** Список инструментов один раз за жизнь процесса: он меняется только с новой версией MCP-сервера. */
	@Override
	public List<ToolSpec> specs() {
		List<ToolSpec> known = specs;
		if (known != null) {
			return known;
		}
		List<ToolSpec> loaded = new ArrayList<>();
		for (JsonNode t : rpc("tools/list", json.createObjectNode()).path("tools")) {
			loaded.add(new ToolSpec(t.path("name").asString(), t.path("description").asString(""),
					json.writeValueAsString(t.path("inputSchema"))));
		}
		specs = List.copyOf(loaded);
		return specs;
	}

	@Override
	public ToolResult call(String name, String argumentsJson) {
		JsonNode args;
		try {
			args = json.readTree(argumentsJson == null || argumentsJson.isBlank() ? "{}" : argumentsJson);
		}
		catch (JacksonException e) {
			return ToolResult.failure("аргументы инструмента " + name + " не разобрались как JSON");
		}
		ObjectNode params = json.createObjectNode().put("name", name);
		params.set("arguments", args);
		JsonNode result = rpc("tools/call", params);
		StringBuilder text = new StringBuilder();
		for (JsonNode block : result.path("content")) {
			if ("text".equals(block.path("type").asString())) {
				text.append(block.path("text").asString());
			}
		}
		JsonNode ui = result.path("structuredContent").path("ui");
		@SuppressWarnings("unchecked")
		Map<String, Object> action = ui.isObject() ? json.convertValue(ui, Map.class) : null;
		return new ToolResult(text.toString(), result.path("isError").asBoolean(false), action);
	}

	private JsonNode rpc(String method, ObjectNode params) {
		ObjectNode request = json.createObjectNode().put("jsonrpc", "2.0").put("id", ids.incrementAndGet())
			.put("method", method);
		request.set("params", params);
		HttpRequest http = HttpRequest.newBuilder(endpoint)
			.timeout(timeout)
			.header("Content-Type", "application/json")
			.header("Accept", "application/json, text/event-stream")
			.header("MCP-Protocol-Version", PROTOCOL)
			.POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(request)))
			.build();
		try {
			HttpResponse<String> response = this.http.send(http, HttpResponse.BodyHandlers.ofString());
			if (response.statusCode() >= 400) {
				throw new AgentFailure("MCP-сервер ответил " + response.statusCode() + " на " + method);
			}
			JsonNode body = json.readTree(response.body());
			if (body.has("error")) {
				throw new AgentFailure("MCP-сервер: " + body.path("error").path("message").asString(method));
			}
			return body.path("result");
		}
		catch (IOException | JacksonException e) {
			throw new AgentFailure("MCP-сервер недоступен (" + endpoint + ")", e);
		}
		catch (InterruptedException e) {
			Thread.currentThread().interrupt();
			throw new AgentFailure("ход агента прерван", e);
		}
	}

}
