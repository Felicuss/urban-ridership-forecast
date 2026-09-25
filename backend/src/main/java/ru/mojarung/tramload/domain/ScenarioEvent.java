package ru.mojarung.tramload.domain;

import java.time.LocalDate;
import java.util.OptionalInt;

/**
 * Событие сценария: перекрытие, стройка, массовое мероприятие. Умножает прогноз маршрута
 * (или всех маршрутов, если маршрут не задан) в датах from-to и часах hours.
 */
public record ScenarioEvent(OptionalInt route, LocalDate from, LocalDate to, HourWindow hours, double multiplier,
		String label) {

	public boolean covers(int route, LocalDate date, int hour) {
		return (this.route.isEmpty() || this.route.getAsInt() == route) && !date.isBefore(from) && !date.isAfter(to)
				&& hours.contains(hour);
	}

}
