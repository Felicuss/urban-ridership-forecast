package ru.mojarung.tramload.api.dto;

import io.swagger.v3.oas.annotations.media.Schema;

/** Параметры прогноза в теле POST-запросов; те же, что у GET /api/v1/forecast. */
@Schema(description = "Что и за какой интервал прогнозировать")
public record ForecastQueryDto(
		@Schema(description = "route, stop, segment или network", example = "route") String level,
		@Schema(description = "маршрут для route и segment, id остановки для stop", example = "17") String id,
		@Schema(description = "направление участка, 0 или 1") Integer direction,
		@Schema(description = "первая остановка участка") String fromStop,
		@Schema(description = "последняя остановка участка") String toStop,
		@Schema(description = "начало интервала", example = "2025-11-03") String from,
		@Schema(description = "конец интервала включительно", example = "2025-11-03") String to,
		@Schema(description = "окно часов суток", example = "7-9") String hours,
		@Schema(description = "hour, day или month") String granularity,
		@Schema(description = "day, month или year") String horizon) {
}
