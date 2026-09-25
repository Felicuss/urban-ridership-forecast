package ru.mojarung.tramload.domain;

import java.time.LocalDate;

/** День шкалы времени: тип дня по производственному календарю, праздник и источник данных. */
public record DayInfo(LocalDate date, int dayOfWeek, String dayType, DayKind kind, boolean dayOff, String holiday,
		Source source) {
}
