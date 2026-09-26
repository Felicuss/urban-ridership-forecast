package ru.mojarung.tramload.api.dto;

import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;

/** Лента сбоев: архив и свежие сообщения канала. */
public record NewsFeedDto(
		List<IncidentDto> incidents,
		@Schema(description = "доля посадок, которую маршрут теряет за час полной остановки", example = "0.5") double alpha,
		@Schema(description = "откуда оценка доли") String alphaSource,
		@Schema(description = "когда читалась живая лента; пусто, если она выключена") String liveCheckedAt,
		@Schema(description = "почему живую ленту прочитать не удалось") String liveError) {
}
