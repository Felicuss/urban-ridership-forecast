package ru.mojarung.tramload.application;

import java.util.List;

import ru.mojarung.tramload.domain.Aggregator.Point;

/** Ряд прогноза объекта: точки с коридором и итог за интервал. */
public record ForecastResult(ResolvedQuery query, List<Point> points, Point total, List<String> notes) {

	public ForecastResult {
		points = List.copyOf(points);
		notes = List.copyOf(notes);
	}

}
