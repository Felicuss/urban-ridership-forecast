package ru.mojarung.tramload.infrastructure.agent;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

import ru.mojarung.tramload.domain.agent.AgentFailure;
import ru.mojarung.tramload.domain.agent.ChatMessage;
import ru.mojarung.tramload.domain.agent.LanguageModel;
import ru.mojarung.tramload.domain.agent.ModelReply;
import ru.mojarung.tramload.domain.agent.ToolCall;
import ru.mojarung.tramload.domain.agent.ToolSpec;

/**
 * Модель через OpenAI-совместимый API chat/completions: Ollama Cloud (https://ollama.com/v1) или любой другой
 * провайдер с вызовом инструментов. Ключ уходит только в заголовок Authorization и нигде не пишется.
 */
final class OpenAiCompatibleModel implements LanguageModel {

	private static final double TEMPERATURE = 0.2;

	private final HttpClient http;
	private final JsonMapper json;
	private final URI endpoint;
	private final String apiKey;
	private final String model;
	private final Duration timeout;

	OpenAiCompatibleModel(HttpClient http, JsonMapper json, String baseUrl, String apiKey, String model, Duration timeout) {
		this.http = http;
		this.json = json;
		this.endpoint = URI.create(baseUrl.replaceAll("/+$", "") + "/chat/completions");
		this.apiKey = apiKey;
		this.model = model;
		this.timeout = timeout;
	}

	@Override
	public ModelReply complete(List<ChatMessage> messages, List<ToolSpec> tools) {
		HttpRequest request = HttpRequest.newBuilder(endpoint)
			.timeout(timeout)
			.header("Authorization", "Bearer " + apiKey)
			.header("Content-Type", "application/json")
			.POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body(messages, tools))))
			.build();
		try {
			HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
			if (response.statusCode() >= 400) {
				throw new AgentFailure("модель ответила " + response.statusCode());
			}
			return reply(json.readTree(response.body()));
		}
		catch (IOException | JacksonException e) {
			throw new AgentFailure("модель недоступна (" + e.getClass().getSimpleName() + ")", e);
		}
		catch (InterruptedException e) {
			Thread.currentThread().interrupt();
			throw new AgentFailure("ход агента прерван", e);
		}
	}

	@Override
	public boolean configured() {
		return true;
	}

	@Override
	public String name() {
		return model;
	}

	private ObjectNode body(List<ChatMessage> messages, List<ToolSpec> tools) {
		ObjectNode body = json.createObjectNode();
		body.put("model", model);
		body.put("temperature", TEMPERATURE);
		ArrayNode list = body.putArray("messages");
		messages.forEach(m -> list.add(message(m)));
		if (!tools.isEmpty()) {
			ArrayNode specs = body.putArray("tools");
			for (ToolSpec t : tools) {
				ObjectNode fn = specs.addObject().put("type", "function").putObject("function");
				fn.put("name", t.name()).put("description", t.description());
				fn.set("parameters", json.readTree(t.parametersJson()));
			}
		}
		else {
			body.put("tool_choice", "none");
		}
		return body;
	}

	private ObjectNode message(ChatMessage m) {
		ObjectNode node = json.createObjectNode().put("role", m.role().name().toLowerCase());
		node.put("content", m.content() == null ? "" : m.content());
		if (m.toolCallId() != null) {
			node.put("tool_call_id", m.toolCallId());
		}
		if (!m.toolCalls().isEmpty()) {
			ArrayNode calls = node.putArray("tool_calls");
			for (ToolCall c : m.toolCalls()) {
				ObjectNode call = calls.addObject().put("id", c.id()).put("type", "function");
				call.putObject("function").put("name", c.name()).put("arguments", c.arguments());
			}
		}
		return node;
	}

	private static ModelReply reply(JsonNode root) {
		JsonNode message = root.path("choices").path(0).path("message");
		if (message.isMissingNode()) {
			throw new AgentFailure("в ответе модели нет choices[0].message");
		}
		List<ToolCall> calls = new ArrayList<>();
		for (JsonNode c : message.path("tool_calls")) {
			calls.add(new ToolCall(c.path("id").asString(), c.path("function").path("name").asString(),
					c.path("function").path("arguments").asString("{}")));
		}
		String content = message.path("content").isNull() ? null : message.path("content").asString(null);
		return new ModelReply(content, calls);
	}

}
