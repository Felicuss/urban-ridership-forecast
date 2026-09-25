package ru.mojarung.tramload.api.dto;

import java.time.LocalDate;
import java.util.List;

/** Кадры тепловой карты: посадки маршрутов и остановок по часам даты. */
public record NetworkLoadResponse(LocalDate date, String source, List<Integer> hours, String timezone, boolean scenario,
		List<SeriesDto> routes, List<SeriesDto> stops) {
}
