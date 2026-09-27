package ru.mojarung.tramload.domain;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.Arrays;
import java.util.List;

/**
 * Шкала времени интерфейса: 01.01.2025 - 31.10.2026. Январь-октябрь 2025 - факт валидаций,
 * ноябрь-декабрь 2025 - прогноз модели (берётся из массива сценария), январь-октябрь 2026 - оценка
 * по сезонному индексу. Факт и оценка лежат в одном неизменяемом массиве маршрут × день × час.
 */
public final class Timeline {

	private final List<Integer> routes;
	private final LocalDate start;
	private final DayInfo[] days;
	private final double[] values;
	private final double[] plan;
	private final ForecastGrid horizon;
	private final int horizonOffset;

	public Timeline(List<DayInfo> days, double[] values, ForecastGrid horizon) {
		this(days, values, null, horizon);
	}

	/**
	 * @param values факт и оценка по индексу (маршрут × день шкалы) × 24 + час; дни прогноза не читаются
	 * @param plan план прошедших дней по тому же индексу: прогноз, сделанный вечером накануне; NaN или null - плана нет
	 */
	public Timeline(List<DayInfo> days, double[] values, double[] plan, ForecastGrid horizon) {
		this.routes = horizon.routes();
		this.days = days.toArray(DayInfo[]::new);
		this.start = this.days[0].date();
		this.values = values.clone();
		this.plan = plan == null ? null : plan.clone();
		this.horizon = horizon;
		this.horizonOffset = (int) ChronoUnit.DAYS.between(start, horizon.start());
		if (values.length != routes.size() * this.days.length * ForecastGrid.HOURS) {
			throw new IllegalArgumentException("шкала: " + values.length + " значений вместо "
					+ routes.size() * this.days.length * ForecastGrid.HOURS);
		}
		if (plan != null && plan.length != values.length) {
			throw new IllegalArgumentException("план: " + plan.length + " значений вместо " + values.length);
		}
		for (int d = 0; d < this.days.length; d++) {
			if (!this.days[d].date().equals(start.plusDays(d))) {
				throw new IllegalArgumentException("в календаре шкалы пропущен день после " + start.plusDays(d - 1L));
			}
			boolean inHorizon = horizon.contains(this.days[d].date());
			if (inHorizon != (this.days[d].source() == Source.FORECAST)) {
				throw new IllegalArgumentException("источник дня " + this.days[d].date() + " не совпадает с горизонтом");
			}
		}
	}

	public LocalDate start() {
		return start;
	}

	public LocalDate end() {
		return days[days.length - 1].date();
	}

	public int size() {
		return days.length;
	}

	public boolean contains(LocalDate date) {
		return !date.isBefore(start) && !date.isAfter(end());
	}

	public int dayIndex(LocalDate date) {
		if (!contains(date)) {
			throw new IllegalArgumentException("дата " + date + " вне шкалы " + start + " - " + end());
		}
		return (int) ChronoUnit.DAYS.between(start, date);
	}

	public DayInfo day(int index) {
		return days[index];
	}

	public List<DayInfo> days() {
		return List.of(days);
	}

	/** Посадки маршрута в час: для горизонта прогноза - из массива сценария, иначе факт или оценка. */
	public double value(int routeIndex, int day, int hour, double[] prediction) {
		return value(routeIndex, day, hour, prediction, List.of());
	}

	/**
	 * То же, но события сценария умножают и оценку 2026 года: перекрытие или мероприятие можно примерить на любой
	 * будущий день. В горизонте прогноза события уже учтены в массиве сценария, факт они не меняют.
	 */
	public double value(int routeIndex, int day, int hour, double[] prediction, List<ScenarioEvent> events) {
		Source source = days[day].source();
		if (source == Source.FORECAST) {
			return prediction[horizon.cell(routeIndex, day - horizonOffset, hour)];
		}
		double v = values[(routeIndex * days.length + day) * ForecastGrid.HOURS + hour];
		if (source == Source.OUTLOOK) {
			int route = routes.get(routeIndex);
			LocalDate date = days[day].date();
			for (ScenarioEvent e : events) {
				if (e.covers(route, date, hour)) {
					v *= e.multiplier();
				}
			}
		}
		return v;
	}

	/** План маршрута на час прошедшего дня: прогноз, сделанный вечером накануне; NaN, если плана нет. */
	public double plan(int routeIndex, int day, int hour) {
		return plan == null ? Double.NaN : plan[(routeIndex * days.length + day) * ForecastGrid.HOURS + hour];
	}

	public int routeIndex(int route) {
		return horizon.routeIndex(route);
	}

	/** Сумма значений маршрута за день по шкале: для проверок согласованности. */
	public double daySum(int routeIndex, int day, double[] prediction) {
		double[] hours = new double[ForecastGrid.HOURS];
		Arrays.setAll(hours, h -> value(routeIndex, day, h, prediction));
		return Arrays.stream(hours).sum();
	}

}
