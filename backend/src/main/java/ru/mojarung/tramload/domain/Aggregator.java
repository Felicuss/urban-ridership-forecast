package ru.mojarung.tramload.domain;

import java.time.LocalDate;
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Сворачивает почасовые значения шкалы в ряд: веса маршрутов задают объект (маршрут, сеть, остановка, участок),
 * даты и окно часов - интервал, шаг - час, сутки или месяц. Сумма точек ряда равна сумме ячеек интервала.
 * Коридор зависит от источника: у факта его нет, у прогноза - множители бэктеста, у оценки - ±12 %.
 * У точек за сутки и месяц есть пик: самый загруженный час внутри точки, по нему видна пиковая нагрузка.
 * У прошедших дней есть план - прогноз, сделанный накануне, свёрнутый с теми же весами; у остальных его нет.
 */
public final class Aggregator {

	/** Коридор оценки по сезонному индексу: ошибка индекса на реальных месяцах доходила до 12,6 %. */
	public static final double OUTLOOK_CORRIDOR = 0.12;
	private static final DateTimeFormatter HOUR_LABEL = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:00");

	private final Timeline timeline;
	private final Intervals intervals;

	public Aggregator(Timeline timeline, Intervals intervals) {
		this.timeline = timeline;
		this.intervals = intervals;
	}

	public List<Point> series(double[] prediction, Map<Integer, Double> weights, LocalDate from, LocalDate to,
			HourWindow hours, Granularity granularity) {
		List<Point> out = new ArrayList<>();
		YearMonth month = null;
		Source monthSource = null;
		double monthSum = 0;
		Peak monthPeak = null;
		double monthPlan = 0;
		for (LocalDate date = from; !date.isAfter(to); date = date.plusDays(1)) {
			int d = timeline.dayIndex(date);
			DayInfo info = timeline.day(d);
			double daySum = 0;
			double dayPlan = 0;
			Peak dayPeak = null;
			for (int h = hours.first(); h <= hours.last(); h++) {
				double v = cellSum(prediction, weights, d, h);
				double plan = planSum(weights, d, h);
				daySum += v;
				dayPlan += plan;
				String label = date.atTime(h, 0).format(HOUR_LABEL);
				dayPeak = Peak.max(dayPeak, new Peak(label, v));
				if (granularity == Granularity.HOUR) {
					out.add(Point.of(label, band(info.source(), v, intervals.hour(h, v)), info.source()).withPlan(plan));
				}
			}
			if (granularity == Granularity.DAY) {
				out.add(Point.of(date.toString(), band(info.source(), daySum, intervals.day(info.kind(), daySum)),
						info.source()).withPeak(dayPeak).withPlan(dayPlan));
			}
			if (granularity == Granularity.MONTH) {
				YearMonth current = YearMonth.from(date);
				if (month != null && !current.equals(month)) {
					out.add(monthPoint(month, monthSum, monthSource, monthPeak).withPlan(monthPlan));
					monthSum = 0;
					monthPeak = null;
					monthPlan = 0;
				}
				month = current;
				monthSource = info.source();
				monthSum += daySum;
				monthPeak = Peak.max(monthPeak, dayPeak);
				monthPlan += dayPlan;
			}
		}
		if (granularity == Granularity.MONTH && month != null) {
			out.add(monthPoint(month, monthSum, monthSource, monthPeak).withPlan(monthPlan));
		}
		return out;
	}

	private Point monthPoint(YearMonth month, double sum, Source source, Peak peak) {
		return Point.of(month.toString(), band(source, sum, intervals.month(sum)), source).withPeak(peak);
	}

	/** План объекта в ячейке день шкалы × час с теми же весами маршрутов; NaN, если у дня нет плана. */
	private double planSum(Map<Integer, Double> weights, int day, int hour) {
		double sum = 0;
		for (Map.Entry<Integer, Double> w : weights.entrySet()) {
			sum += w.getValue() * timeline.plan(timeline.routeIndex(w.getKey()), day, hour);
		}
		return sum;
	}

	private static Intervals.Band band(Source source, double value, Intervals.Band forecast) {
		return switch (source) {
			case FACT -> new Intervals.Band(value, value, value);
			case FORECAST -> forecast;
			case OUTLOOK -> new Intervals.Band(value, value * (1 - OUTLOOK_CORRIDOR), value * (1 + OUTLOOK_CORRIDOR));
		};
	}

	/** Значение объекта в ячейке день шкалы × час: сумма маршрутов с весами. */
	public double cellSum(double[] prediction, Map<Integer, Double> weights, int day, int hour) {
		double sum = 0;
		for (Map.Entry<Integer, Double> w : weights.entrySet()) {
			sum += w.getValue() * timeline.value(timeline.routeIndex(w.getKey()), day, hour, prediction);
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
		Source source = points.isEmpty() ? Source.FORECAST : points.getFirst().source();
		boolean mixed = points.stream().anyMatch(p -> p.source() != source);
		Peak peak = null;
		double plan = 0;
		for (Point p : points) {
			peak = Peak.max(peak, p.peak());
			plan += p.plan() == null ? Double.NaN : p.plan();
		}
		Double totalPlan = points.isEmpty() || Double.isNaN(plan) ? null : plan;
		return new Point("total", p50, p10, p90, mixed ? Source.FORECAST : source, peak, totalPlan);
	}

	/**
	 * Точка ряда; peak - самый загруженный час внутри точки, у почасовых точек его нет;
	 * plan - план прошедших дней, если он есть у всех ячеек точки, иначе null.
	 */
	public record Point(String period, double p50, double p10, double p90, Source source, Peak peak, Double plan) {

		public static Point of(String period, Intervals.Band band, Source source) {
			return new Point(period, band.p50(), band.p10(), band.p90(), source, null, null);
		}

		public Point withPeak(Peak value) {
			return new Point(period, p50, p10, p90, source, value, plan);
		}

		public Point withPlan(double value) {
			return new Point(period, p50, p10, p90, source, peak, Double.isNaN(value) ? null : value);
		}

	}

	/** Пиковый час: метка часа вида 2025-11-14T08:00 и посадки в этот час. */
	public record Peak(String at, double value) {

		/** Больший из двух пиков; при равенстве остаётся более ранний. */
		static Peak max(Peak a, Peak b) {
			if (a == null) {
				return b;
			}
			return b != null && b.value() > a.value() ? b : a;
		}

	}

}
