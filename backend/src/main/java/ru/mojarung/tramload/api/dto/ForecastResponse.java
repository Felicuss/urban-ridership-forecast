package ru.mojarung.tramload.api.dto;

import java.time.LocalDate;
import java.util.List;

/** Ряд прогноза посадок. Время местное, Europe/Moscow. */
public record ForecastResponse(TargetDto target, String horizon, String granularity, LocalDate from, LocalDate to,
		String hours, String timezone, String unit, List<PointDto> points, PointDto total, List<String> notes) {
}
