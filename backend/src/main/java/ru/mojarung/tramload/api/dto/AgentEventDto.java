package ru.mojarung.tramload.api.dto;

import java.util.Map;

import io.swagger.v3.oas.annotations.media.Schema;
import ru.mojarung.tramload.domain.agent.AgentEvent;

/** Событие хода агента в потоке SSE. */
public record AgentEventDto(
		@Schema(description = "step, ui, answer или error") String type,
		String text,
		@Schema(description = "инструмент для step и ui") String tool,
		@Schema(description = "команда интерфейсу для ui: type show, layers или ride и параметры") Map<String, Object> action) {

	public static AgentEventDto of(AgentEvent e) {
		return new AgentEventDto(e.type().name().toLowerCase(), e.text(), e.tool(), e.action());
	}

}
