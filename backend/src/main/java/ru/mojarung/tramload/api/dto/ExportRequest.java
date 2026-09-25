package ru.mojarung.tramload.api.dto;

import java.util.List;
import java.util.Map;

import io.swagger.v3.oas.annotations.media.Schema;

/** Выгрузка по сценарию: то же, что GET /api/v1/export, плюс ползунки и события. */
public record ExportRequest(
		@Schema(description = "csv или xlsx", example = "xlsx") String format,
		@Schema(description = "route, stop, segment или network", example = "route") String level,
		@Schema(description = "пусто - все объекты уровня; для участка один маршрут") List<String> ids,
		@Schema(description = "направление участка, 0 или 1") Integer direction,
		@Schema(description = "первая остановка участка") String fromStop,
		@Schema(description = "последняя остановка участка") String toStop,
		String from,
		String to,
		String hours,
		String granularity,
		String horizon,
		Map<String, Object> coefficients,
		List<EventDto> events) {
}
