package ru.mojarung.tramload.api.dto;

import java.util.List;
import java.util.Map;

import io.swagger.v3.oas.annotations.media.Schema;

/** Выгрузка по сценарию: то же, что GET /api/v1/export, плюс ползунки и события. */
public record ExportRequest(
		@Schema(description = "csv или xlsx", example = "xlsx") String format,
		@Schema(description = "route, stop или network", example = "route") String level,
		@Schema(description = "пусто - все объекты уровня") List<String> ids,
		String from,
		String to,
		String hours,
		String granularity,
		String horizon,
		Map<String, Object> coefficients,
		List<EventDto> events) {
}
