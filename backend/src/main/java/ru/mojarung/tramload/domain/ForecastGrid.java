package ru.mojarung.tramload.domain;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.List;

/**
 * Сетка прогноза маршрут × дата × час. Ячейка - индекс в плоском массиве: (маршрут × дни + день) × 24 + час,
 * поэтому срез интервала - арифметика индексов без поиска.
 */
public record ForecastGrid(List<Integer> routes, LocalDate start, int days) {

	public static final int HOURS = 24;

	public ForecastGrid {
		routes = List.copyOf(routes);
		if (routes.isEmpty() || days <= 0) {
			throw new IllegalArgumentException("пустая сетка прогноза");
		}
	}

	public int size() {
		return routes.size() * days * HOURS;
	}

	public LocalDate end() {
		return start.plusDays(days - 1L);
	}

	public boolean hasRoute(int route) {
		return routes.contains(route);
	}

	public boolean contains(LocalDate date) {
		return !date.isBefore(start) && !date.isAfter(end());
	}

	public int routeIndex(int route) {
		int index = routes.indexOf(route);
		if (index < 0) {
			throw new IllegalArgumentException("маршрута " + route + " нет в сетке");
		}
		return index;
	}

	public int dayIndex(LocalDate date) {
		if (!contains(date)) {
			throw new IllegalArgumentException("дата " + date + " вне горизонта " + start + " - " + end());
		}
		return (int) ChronoUnit.DAYS.between(start, date);
	}

	public LocalDate date(int dayIndex) {
		return start.plusDays(dayIndex);
	}

	public int cell(int routeIndex, int dayIndex, int hour) {
		return (routeIndex * days + dayIndex) * HOURS + hour;
	}

}
