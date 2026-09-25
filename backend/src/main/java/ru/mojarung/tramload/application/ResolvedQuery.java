package ru.mojarung.tramload.application;

import java.time.LocalDate;

import ru.mojarung.tramload.domain.Granularity;
import ru.mojarung.tramload.domain.HourWindow;

/** Проверенный запрос: объект найден, даты внутри горизонта, шаг и окно часов выбраны. */
public record ResolvedQuery(Target target, LocalDate from, LocalDate to, HourWindow hours, Granularity granularity,
		Horizon horizon) {

	public boolean isYear() {
		return horizon == Horizon.YEAR;
	}

}
