package ru.mojarung.tramload.api.dto;

import io.swagger.v3.oas.annotations.media.Schema;

/** Событие сценария: перекрытие, стройка, мероприятие. */
@Schema(description = "Событие: умножает прогноз маршрута (или всех, если маршрут не задан) в датах и часах")
public record EventDto(
		@Schema(description = "маршрут; пусто - все маршруты", example = "17") Integer route,
		@Schema(example = "2025-11-22") String from,
		@Schema(example = "2025-11-23") String to,
		@Schema(description = "окно часов, пусто - весь день", example = "10-18") String hours,
		@Schema(description = "0 - перекрытие, 1.2 - рост на 20 %", example = "0") Double multiplier,
		@Schema(example = "Перекрытие на Сущёвском Валу") String label) {
}
