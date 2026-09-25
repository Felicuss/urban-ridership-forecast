package ru.mojarung.tramload.api.dto;

import java.util.List;
import java.util.Map;

import io.swagger.v3.oas.annotations.media.Schema;

/** Сценарий: переопределения ползунков и события поверх прогноза по умолчанию. */
@Schema(description = "Пересчёт прогноза с другими коэффициентами и событиями")
public record ScenarioRequest(
		ForecastQueryDto query,
		@Schema(description = "ключ ползунка из /api/v1/coefficients -> значение", example = "{\"level_dec\": 1.05}")
		Map<String, Object> coefficients,
		List<EventDto> events) {
}
