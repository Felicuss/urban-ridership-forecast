package ru.mojarung.tramload.application;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

import ru.mojarung.tramload.domain.Aggregator.Point;
import ru.mojarung.tramload.domain.ForecastModel;
import ru.mojarung.tramload.domain.Granularity;
import ru.mojarung.tramload.domain.HourWindow;
import ru.mojarung.tramload.domain.Scenario;
import ru.mojarung.tramload.domain.Source;
import ru.mojarung.tramload.domain.ValidationException;
import ru.mojarung.tramload.domain.network.Stop;

/**
 * Таблица для выгрузки: объект × период с прогнозом и коридором. Строки собираются лениво по объектам,
 * поэтому полная сетка «остановка × час» (около 660 тыс. строк) не держится в памяти целиком.
 */
public final class ExportService {

	private static final Map<Source, String> SOURCE_LABEL = Map.of(Source.FACT, "факт", Source.FORECAST, "прогноз",
			Source.OUTLOOK, "оценка");

	/** Лист Excel вмещает 1 048 576 строк, одна уходит на заголовок. */
	public static final long MAX_ROWS = 1_048_575;
	public static final List<String> HEADER = List.of("уровень", "объект", "название", "период", "прогноз", "p10",
			"p90", "источник");

	private final ForecastModel model;
	private final QueryResolver resolver;
	private final ForecastService forecasts;

	public ExportService(ForecastModel model, QueryResolver resolver, ForecastService forecasts) {
		this.model = model;
		this.resolver = resolver;
		this.forecasts = forecasts;
	}

	public ExportTable table(ExportQuery q, Scenario scenario) {
		if (q.level() == null || q.level() == Level.SEGMENT) {
			throw ValidationException.of("level", "выгрузка доступна для route, stop и network");
		}
		List<String> ids = q.ids().isEmpty() ? allIds(q.level()) : q.ids();
		List<Target> targets = ids.stream().map(id -> resolver.target(query(q, id))).toList();
		ResolvedQuery first = resolver.resolve(query(q, ids.getFirst()));
		long perTarget = forecasts.forecast(first, scenario).points().size();
		long rows = perTarget * targets.size();
		if (rows > MAX_ROWS) {
			throw ValidationException.of("granularity", "в выгрузке " + rows + " строк, лист Excel вмещает " + MAX_ROWS
					+ ": сузьте интервал или возьмите шаг day");
		}
		Stream<ExportRow> stream = targets.stream().flatMap(t -> rowsOf(first, t, scenario));
		return new ExportTable(fileName(q.level(), ids, first.from(), first.to()), stream, rows);
	}

	private Stream<ExportRow> rowsOf(ResolvedQuery base, Target target, Scenario scenario) {
		ResolvedQuery q = new ResolvedQuery(target, base.from(), base.to(), base.hours(), base.granularity(),
				base.horizon());
		int decimals = target.isEstimate() ? 1 : 0;
		return forecasts.forecast(q, scenario).points().stream()
			.map(p -> ExportRow.of(target, p, decimals));
	}

	private List<String> allIds(Level level) {
		return switch (level) {
			case ROUTE -> model.grid().routes().stream().map(String::valueOf).toList();
			case STOP -> model.network().stops().stream().map(Stop::id).toList();
			default -> List.of("all");
		};
	}

	private static ForecastQuery query(ExportQuery q, String id) {
		return new ForecastQuery(q.level(), id, null, null, null, q.from(), q.to(), q.hours(), q.granularity(),
				q.horizon());
	}

	private static String fileName(Level level, List<String> ids, LocalDate from, LocalDate to) {
		String what = switch (level) {
			case ROUTE -> ids.size() == 1 ? "маршрут_" + ids.getFirst() : "маршруты";
			case STOP -> ids.size() == 1 ? "остановка_" + ids.getFirst() : "остановки";
			default -> "сеть";
		};
		return "прогноз_посадок_" + what + "_" + from + "_" + to;
	}

	/** Что выгружать: пустой ids - все объекты уровня. */
	public record ExportQuery(Level level, List<String> ids, LocalDate from, LocalDate to, HourWindow hours,
			Granularity granularity, Horizon horizon) {

		public ExportQuery {
			ids = ids == null ? List.of() : List.copyOf(ids);
		}

	}

	/** Таблица выгрузки. rows - ленивый поток, его можно прочитать один раз. */
	public record ExportTable(String fileBaseName, Stream<ExportRow> rows, long rowCount) {
	}

	/** Строка выгрузки. decimals: 0 для маршрутов и сети (как в сабмите), 1 для остановок. */
	public record ExportRow(String level, String id, String name, String period, double p50, double p10, double p90,
			int decimals, String source) {

		static ExportRow of(Target t, Point p, int decimals) {
			return new ExportRow(t.level().code(), t.id(), t.name(), p.period(), round(p.p50(), decimals),
					round(p.p10(), decimals), round(p.p90(), decimals), decimals, SOURCE_LABEL.get(p.source()));
		}

		private static double round(double value, int decimals) {
			return decimals == 0 ? Math.rint(value) : Math.rint(value * 10.0) / 10.0;
		}

	}

}
