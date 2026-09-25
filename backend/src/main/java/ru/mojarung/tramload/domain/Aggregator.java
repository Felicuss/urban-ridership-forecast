package ru.mojarung.tramload.domain;

import java.time.LocalDate;
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Сворачивает почасовой прогноз в ряд: веса маршрутов задают объект (маршрут, сеть, остановка, участок),
 * даты и окно часов - интервал, шаг - час, сутки или месяц. Сумма точек ряда равна сумме ячеек интервала.
 */
public final class Aggregator {

	private static final DateTimeFormatter HOUR_LABEL = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:00");

	private final ForecastComponents components;
	private final Intervals intervals;

	public Aggregator(ForecastComponents components, Intervals intervals) {
		this.components = components;
		this.intervals = intervals;
	}

	public List<Point> series(double[] prediction, Map<Integer, Double> weights, LocalDate from, LocalDate to,
			HourWindow hours, Granularity granularity) {
		ForecastGrid grid = components.grid();
		List<Point> out = new ArrayList<>();
		YearMonth month = null;
		double monthSum = 0;
		for (LocalDate date = from; !date.isAfter(to); date = date.plusDays(1)) {
			int d = grid.dayIndex(date);
			double daySum = 0;
			for (int h = hours.first(); h <= hours.last(); h++) {
				double v = cellSum(prediction, weights, d, h);
				daySum += v;
				if (granularity == Granularity.HOUR) {
					out.add(Point.of(date.atTime(h, 0).format(HOUR_LABEL), intervals.hour(h, v)));
				}
			}
			if (granularity == Granularity.DAY) {
				out.add(Point.of(date.toString(), intervals.day(components.dayKind(d), daySum)));
			}
			if (granularity == Granularity.MONTH) {
				YearMonth current = YearMonth.from(date);
				if (month != null && !current.equals(month)) {
					out.add(Point.of(month.toString(), intervals.month(monthSum)));
					monthSum = 0;
				}
				month = current;
				monthSum += daySum;
			}
		}
		if (granularity == Granularity.MONTH && month != null) {
			out.add(Point.of(month.toString(), intervals.month(monthSum)));
		}
		return out;
	}

	/** Прогноз объекта в ячейке дата × час: сумма маршрутов с весами. */
	public double cellSum(double[] prediction, Map<Integer, Double> weights, int dayIndex, int hour) {
		ForecastGrid grid = components.grid();
		double sum = 0;
		for (Map.Entry<Integer, Double> w : weights.entrySet()) {
			sum += w.getValue() * prediction[grid.cell(grid.routeIndex(w.getKey()), dayIndex, hour)];
		}
		return sum;
	}

	/** Итог ряда: сумма точек. Коридор итога - сумма коридоров точек, то есть с запасом. */
	public static Point total(List<Point> points) {
		double p50 = 0;
		double p10 = 0;
		double p90 = 0;
		for (Point p : points) {
			p50 += p.p50();
			p10 += p.p10();
			p90 += p.p90();
		}
		return new Point("total", p50, p10, p90);
	}

	public record Point(String period, double p50, double p10, double p90) {

		public static Point of(String period, Intervals.Band band) {
			return new Point(period, band.p50(), band.p10(), band.p90());
		}

	}

}
