package ru.mojarung.tramload.api.dto;

import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;

/** Сбой движения из канала Дептранса и его события сценария. */
@Schema(description = "Сбой: сообщение «задерживаются трамваи» и ответ «движение восстановлено»")
public record IncidentDto(
		@Schema(description = "номер сообщения в канале", example = "23459") String id,
		@Schema(example = "[12]") List<Integer> routes,
		@Schema(description = "начало, время публикации сообщения", example = "2025-11-08T10:28:51+03:00") String start,
		@Schema(description = "конец; пусто, пока движение не восстановлено", example = "2025-11-08T11:09:05+03:00") String end,
		@Schema(example = "40.2") Double minutes,
		@Schema(example = "technical_or_unspecified") String cause,
		@Schema(example = "технические причины") String causeLabel,
		@Schema(example = "В районе Авиамоторной и 3-й Владимирской улиц по техническим причинам") String location,
		@Schema(example = "https://t.me/DtOperativno/23459") String sourceUrl,
		String recoveryUrl,
		@Schema(description = "день сбоя в горизонте: сбой уже учтён в прогнозе по умолчанию") boolean inForecast,
		@Schema(description = "archive - проверенный архив 2025 года, live - свежая лента канала") String origin,
		@Schema(description = "события сценария на день сбоя; пусто вне горизонта прогноза") List<EventDto> events) {
}
