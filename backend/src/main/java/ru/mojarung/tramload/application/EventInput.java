package ru.mojarung.tramload.application;

import java.time.LocalDate;

import ru.mojarung.tramload.domain.HourWindow;

/**
 * Событие сценария из запроса: перекрытие (multiplier 0), стройка или мероприятие.
 *
 * @param route маршрут; если не задан, событие действует на все маршруты
 * @param hours окно часов; если не задано, весь день
 */
public record EventInput(Integer route, LocalDate from, LocalDate to, HourWindow hours, Double multiplier,
		String label) {
}
