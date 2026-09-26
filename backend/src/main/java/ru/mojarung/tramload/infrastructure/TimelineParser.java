package ru.mojarung.tramload.infrastructure;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

import ru.mojarung.tramload.domain.DayInfo;
import ru.mojarung.tramload.domain.DayKind;
import ru.mojarung.tramload.domain.ForecastGrid;
import ru.mojarung.tramload.domain.Source;
import ru.mojarung.tramload.domain.Timeline;

/**
 * Шкала времени из timeline_calendar.csv, actuals.csv (факт 2025), outlook.csv (оценка 2026) и plan.csv
 * (план прошедших дней: прогноз, сделанный накануне). Каждая ячейка факта и оценки должна быть заполнена
 * ровно один раз, иначе запуск останавливается; у плана повтор ячейки тоже ошибка, а пропуск значит «плана нет».
 */
final class TimelineParser {

	private TimelineParser() {
	}

	static Timeline timeline(Path dir, ForecastGrid horizon) {
		List<DayInfo> days = CsvRows.read(dir.resolve("timeline_calendar.csv")).stream()
			.map(TimelineParser::day)
			.toList();
		LocalDate start = days.getFirst().date();
		int routes = horizon.routes().size();
		double[] values = new double[routes * days.size() * ForecastGrid.HOURS];
		boolean[] seen = new boolean[values.length];
		fill(CsvRows.read(dir.resolve("actuals.csv")), "boardings", horizon, start, days.size(), values, seen);
		fill(CsvRows.read(dir.resolve("outlook.csv")), "p50", horizon, start, days.size(), values, seen);
		for (int d = 0; d < days.size(); d++) {
			if (days.get(d).source() == Source.FORECAST) {
				continue;
			}
			for (int r = 0; r < routes; r++) {
				for (int h = 0; h < ForecastGrid.HOURS; h++) {
					if (!seen[(r * days.size() + d) * ForecastGrid.HOURS + h]) {
						throw new ArtifactValidationException("шкала: нет значения маршрута " + horizon.routes().get(r)
								+ " на " + days.get(d).date() + " " + h + ":00");
					}
				}
			}
		}
		double[] plan = new double[values.length];
		Arrays.fill(plan, Double.NaN);
		Path planFile = dir.resolve("plan.csv");
		if (Files.exists(planFile)) {
			fill(CsvRows.read(planFile), "plan", horizon, start, days.size(), plan, new boolean[plan.length]);
		}
		return new Timeline(days, values, plan, horizon);
	}

	private static DayInfo day(Map<String, String> r) {
		String holiday = r.get("holiday");
		return new DayInfo(LocalDate.parse(CsvRows.required(r, "date")), CsvRows.integer(r, "dow"),
				CsvRows.required(r, "day_type"), DayKind.parse(CsvRows.required(r, "kind")),
				Boolean.parseBoolean(CsvRows.required(r, "day_off")), holiday == null || holiday.isBlank() ? null : holiday,
				Source.parse(CsvRows.required(r, "source")));
	}

	private static void fill(List<Map<String, String>> rows, String column, ForecastGrid horizon, LocalDate start,
			int days, double[] values, boolean[] seen) {
		for (Map<String, String> row : rows) {
			int r = horizon.routeIndex(CsvRows.integer(row, "route"));
			int d = (int) ChronoUnit.DAYS.between(start, LocalDate.parse(CsvRows.required(row, "date")));
			int cell = (r * days + d) * ForecastGrid.HOURS + CsvRows.integer(row, "hour");
			if (seen[cell]) {
				throw new ArtifactValidationException("шкала: ячейка повторяется " + row);
			}
			seen[cell] = true;
			values[cell] = CsvRows.number(row, column);
		}
	}

}
