package ru.mojarung.tramload.application;

import java.time.LocalDate;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import ru.mojarung.tramload.domain.ForecastGrid;
import ru.mojarung.tramload.domain.ForecastModel;
import ru.mojarung.tramload.domain.Granularity;
import ru.mojarung.tramload.domain.HourWindow;
import ru.mojarung.tramload.domain.Timeline;
import ru.mojarung.tramload.domain.ValidationException;
import ru.mojarung.tramload.domain.ValidationException.Violation;

/**
* Проверяет запрос против области определения модели и заполняет умолчания по горизонту:
* день - сутки по часам, неделя - 7 суток от from по дням, месяц - месяц по дням,
* год - 12 месяцев от месяца from (без from: ноябрь 2025 - октябрь 2026) по месяцам.
* Все нарушения собираются в одну ошибку, чтобы клиент исправил запрос за один раз.
*/
public final class QueryResolver {

	private static final int WEEK_DAYS = 7;

	private final ForecastModel model;

	public QueryResolver(ForecastModel model) {
		this.model = model;
	}

	public ResolvedQuery resolve(ForecastQuery q) {
		List<Violation> violations = new ArrayList<>();
		if (q.level() == null) {
			throw ValidationException.of("level", "укажите route, stop, segment или network");
		}
		Target target = null;
		try {
			target = target(q);
		}
		catch (ValidationException ex) {
			violations.addAll(ex.violations());
		}
		Horizon horizon = q.horizon();
		Granularity granularity = granularity(q, violations);
		LocalDate[] range = horizon == Horizon.YEAR ? yearRange(q, violations) : range(q, violations);
		if (!violations.isEmpty()) {
			throw new ValidationException(violations);
		}
		HourWindow hours = q.hours() != null ? q.hours() : HourWindow.ALL_DAY;
		return new ResolvedQuery(target, range[0], range[1], hours, granularity, horizon);
	}

	private LocalDate[] range(ForecastQuery q, List<Violation> violations) {
		LocalDate from = q.from() != null ? q.from() : grid().start();
		LocalDate to = q.to() != null ? q.to() : from;
		if (q.horizon() == Horizon.DAY) {
			to = from;
		}
		if (q.horizon() == Horizon.WEEK) {
			to = min(from.plusDays(WEEK_DAYS - 1), timeline().end());
		}
		if (q.horizon() == Horizon.MONTH) {
			YearMonth month = YearMonth.from(from);
			if (month.atEndOfMonth().isBefore(timeline().start()) || month.atDay(1).isAfter(timeline().end())) {
				violations.add(new Violation("from", "месяц " + month + " вне шкалы " + timeline().start()
						+ " - " + timeline().end()));
				return new LocalDate[] { from, from };
			}
			from = max(month.atDay(1), timeline().start());
			to = min(month.atEndOfMonth(), timeline().end());
		}
		checkDates(from, to, q.to() != null && q.horizon() == null, violations);
		return new LocalDate[] { from, to };
	}

	/** До 12 месяцев от месяца from, ограниченных концом шкалы; без from — исходный год прогноза. */
	private LocalDate[] yearRange(ForecastQuery q, List<Violation> violations) {
		if (q.hours() != null && !q.hours().equals(HourWindow.ALL_DAY)) {
			violations.add(new Violation("hours", "годовой прогноз считается по суткам целиком, окно часов не задаётся"));
		}
		LocalDate from = q.from() != null ? q.from().withDayOfMonth(1) : grid().start();
		LocalDate to = min(from.plusYears(1).minusDays(1), timeline().end());
		checkDates(from, to, true, violations);
		return new LocalDate[] { from, to };
	}

	public Target target(ForecastQuery q) {
		return switch (q.level()) {
			case ROUTE -> {
				int route = route(q.id());
				yield new Target(Level.ROUTE, String.valueOf(route), "Маршрут " + route, Map.of(route, 1.0));
			}
			case NETWORK -> new Target(Level.NETWORK, "all", "Все маршруты",
					grid().routes().stream().collect(Collectors.toMap(Function.identity(), r -> 1.0)));
			case STOP -> {
				String id = required(q.id(), "id", "укажите id остановки");
				String name = model.network().stop(id).map(s -> s.name()).orElse(id);
				yield new Target(Level.STOP, id, name, model.network().stopWeights(id));
			}
			case SEGMENT -> segment(q);
		};
	}

	private Target segment(ForecastQuery q) {
		int route = route(q.id());
		if (q.direction() == null) {
			throw ValidationException.of("direction", "для участка укажите направление 0 или 1");
		}
		String from = required(q.fromStop(), "fromStop", "укажите первую остановку участка");
		String to = required(q.toStop(), "toStop", "укажите последнюю остановку участка");
		Map<Integer, Double> weights = model.network().segmentWeights(route, q.direction(), from, to);
		String name = "Маршрут " + route + ": " + stopName(from) + " - " + stopName(to);
		return new Target(Level.SEGMENT, route + ":" + q.direction() + ":" + from + "-" + to, name, weights);
	}

	private Granularity granularity(ForecastQuery q, List<Violation> violations) {
		if (q.horizon() == Horizon.YEAR) {
			if (q.granularity() != null && q.granularity() != Granularity.MONTH) {
				violations.add(new Violation("granularity", "для горизонта year доступен только шаг month"));
			}
			return Granularity.MONTH;
		}
		if (q.granularity() != null) {
			return q.granularity();
		}
		return q.horizon() == Horizon.MONTH || q.horizon() == Horizon.WEEK ? Granularity.DAY : Granularity.HOUR;
	}

	/** Конец интервала проверяем отдельно, только если клиент его задал: иначе он повторяет начало. */
	private void checkDates(LocalDate from, LocalDate to, boolean explicitTo, List<Violation> violations) {
		String range = timeline().start() + " - " + timeline().end();
		if (!timeline().contains(from)) {
			violations.add(new Violation("from", "дата " + from + " вне шкалы " + range
					+ ": факт с января 2025, прогноз ноября-декабря 2025, оценка до декабря 2027"));
		}
		if (explicitTo && !timeline().contains(to)) {
			violations.add(new Violation("to", "дата " + to + " вне шкалы " + range));
		}
		if (explicitTo && from.isAfter(to)) {
			violations.add(new Violation("to", "конец интервала раньше начала"));
		}
	}

	private int route(String id) {
		String value = required(id, "id", "укажите номер маршрута");
		try {
			int route = Integer.parseInt(value);
			if (grid().hasRoute(route)) {
				return route;
			}
		}
		catch (NumberFormatException ignored) {
			// ниже общий ответ: номер не из списка маршрутов
		}
		throw ValidationException.of("id", "маршрута " + value + " нет в прогнозе, доступны " + grid().routes());
	}

	private String stopName(String id) {
		return model.network().stop(id).map(s -> s.name()).orElse(id);
	}

	private ForecastGrid grid() {
		return model.grid();
	}

	private Timeline timeline() {
		return model.timeline();
	}

	private static String required(String value, String field, String message) {
		if (value == null || value.isBlank()) {
			throw ValidationException.of(field, message);
		}
		return value;
	}

	private static LocalDate max(LocalDate a, LocalDate b) {
		return a.isAfter(b) ? a : b;
	}

	private static LocalDate min(LocalDate a, LocalDate b) {
		return a.isBefore(b) ? a : b;
	}

}
