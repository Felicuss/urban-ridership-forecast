package ru.mojarung.tramload.api.dto;

import java.time.LocalDate;

/** День шкалы: dayType - workday, saturday, sunday или holiday; source - fact, forecast или outlook. */
public record CalendarDayDto(LocalDate date, int dayOfWeek, String dayType, String kind, boolean dayOff, String holiday,
		String source) {
}
