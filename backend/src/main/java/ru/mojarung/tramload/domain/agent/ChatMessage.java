package ru.mojarung.tramload.domain.agent;

import java.util.List;

/** Сообщение диалога с моделью. У ответа модели бывают вызовы инструментов, у ответа инструмента - id вызова. */
public record ChatMessage(Role role, String content, String toolCallId, List<ToolCall> toolCalls) {

	public enum Role {
		SYSTEM, USER, ASSISTANT, TOOL
	}

	public ChatMessage {
		toolCalls = toolCalls == null ? List.of() : List.copyOf(toolCalls);
	}

	public static ChatMessage system(String text) {
		return new ChatMessage(Role.SYSTEM, text, null, List.of());
	}

	public static ChatMessage user(String text) {
		return new ChatMessage(Role.USER, text, null, List.of());
	}

	public static ChatMessage assistant(String text) {
		return new ChatMessage(Role.ASSISTANT, text, null, List.of());
	}

	public static ChatMessage calls(String text, List<ToolCall> calls) {
		return new ChatMessage(Role.ASSISTANT, text, null, calls);
	}

	public static ChatMessage tool(String callId, String text) {
		return new ChatMessage(Role.TOOL, text, callId, List.of());
	}

}
