package ru.mojarung.tramload.domain.agent;

import java.util.Map;

/** Ответ инструмента: текст для модели, признак ошибки и команда интерфейсу, если это ui_* инструмент. */
public record ToolResult(String text, boolean error, Map<String, Object> ui) {

	public ToolResult {
		ui = ui == null ? null : Map.copyOf(ui);
	}

	public static ToolResult failure(String text) {
		return new ToolResult(text, true, null);
	}

}
