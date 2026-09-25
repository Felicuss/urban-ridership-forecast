package ru.mojarung.tramload.api.dto;

import java.util.Map;

import io.swagger.v3.oas.annotations.media.Schema;

/** Вопрос агенту: сессия для истории диалога, текст и что сейчас открыто на экране. */
public record AgentChatRequest(
		@Schema(description = "идентификатор диалога, 8-64 символа: латиница, цифры, - и _", example = "b3f1c2d4-e5f6")
		String session,
		@Schema(description = "вопрос, до 1000 символов", example = "Покажи 17 маршрут завтра в 8 утра") String message,
		@Schema(description = "экран: date, hour, route, stop, view, tab, horizon") Map<String, Object> context) {
}
