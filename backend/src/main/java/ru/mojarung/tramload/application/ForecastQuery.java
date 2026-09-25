package ru.mojarung.tramload.application;

import java.time.LocalDate;

import ru.mojarung.tramload.domain.Granularity;
import ru.mojarung.tramload.domain.HourWindow;

/**
 * Запрос прогноза в том виде, как его прислал клиент: всё, кроме уровня, может быть не задано,
 * недостающее заполняет {@link QueryResolver} по горизонту.
 *
 * @param id номер маршрута для route и segment, id остановки для stop, для network не нужен
 * @param direction направление участка (0 или 1)
 * @param fromStop первая остановка участка по ходу рейса
 * @param toStop последняя остановка участка
 * @param hours окно часов суток, например 7-9 для утреннего пика
 */
public record ForecastQuery(Level level, String id, Integer direction, String fromStop, String toStop, LocalDate from,
		LocalDate to, HourWindow hours, Granularity granularity, Horizon horizon) {
}
