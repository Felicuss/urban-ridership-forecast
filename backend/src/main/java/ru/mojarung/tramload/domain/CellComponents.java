package ru.mojarung.tramload.domain;

import java.time.LocalDate;

/** Одна строка forecast_components.csv: всё, что нужно формуле для ячейки маршрут × дата × час. */
public record CellComponents(
		int route,
		LocalDate date,
		int hour,
		int dayOfWeek,
		DayKind kind,
		boolean holiday,
		boolean workingSaturday,
		boolean preNewYear,
		boolean newYearEve,
		double base,
		double baseRestored,
		boolean restorable,
		double route5Shape,
		double precipDay,
		double precipHour,
		double tempDay,
		double prediction) {
}
