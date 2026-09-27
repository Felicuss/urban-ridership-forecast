package ru.mojarung.tramload.domain;

import java.time.YearMonth;
import java.util.List;
import java.util.Map;

/**
 * Горизонт «год»: помесячный прогноз маршрутов с ноября 2025 по декабрь 2027 (forecast_year.csv).
 * Ноябрь и декабрь - суммы почасового прогноза, дальше сезонный индекс городского трамвая, коридор ±12 %.
 */
public record YearForecast(List<Row> rows) {

	public YearForecast {
		rows = List.copyOf(rows);
	}

	public List<YearMonth> months() {
		return rows.stream().map(Row::month).distinct().sorted().toList();
	}

	/** Сумма по маршрутам с весами (1 для маршрута и сети, доли для остановки и участка). */
	public Intervals.Band total(YearMonth month, Map<Integer, Double> weights) {
		double p50 = 0;
		double p10 = 0;
		double p90 = 0;
		for (Row row : rows) {
			Double w = weights.get(row.route());
			if (w != null && row.month().equals(month)) {
				p50 += w * row.p50();
				p10 += w * row.p10();
				p90 += w * row.p90();
			}
		}
		return new Intervals.Band(p50, p10, p90);
	}

	public record Row(int route, YearMonth month, double p50, double p10, double p90, String method) {
	}

}
