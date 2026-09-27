package ru.mojarung.tramload.api.dto;

import java.util.List;
import java.util.Map;

import io.swagger.v3.oas.annotations.media.Schema;

/** Разбор прогноза за сутки по шагам формулы, с ползунками и событиями сценария или без них. */
@Schema(description = "Из чего сложился прогноз маршрута или сети за сутки")
public record ExplainRequest(
		@Schema(description = "маршрут; пусто - вся сеть", example = "17") Integer route,
		@Schema(example = "2025-11-18") String date,
		@Schema(description = "ключ ползунка из /api/v1/coefficients -> значение", example = "{\"level_nov\": 1.02}")
		Map<String, Object> coefficients,
		List<EventDto> events) {
}
