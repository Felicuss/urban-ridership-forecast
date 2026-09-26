package ru.mojarung.tramload.domain.agent;

import java.util.List;

/** Ответ модели: текст или просьба вызвать инструменты. */
public record ModelReply(String content, List<ToolCall> toolCalls) {

	public ModelReply {
		toolCalls = toolCalls == null ? List.of() : List.copyOf(toolCalls);
	}

	public boolean wantsTools() {
		return !toolCalls.isEmpty();
	}

}
