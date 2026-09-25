package ru.mojarung.tramload.domain;

import java.util.EnumMap;
import java.util.Map;

/**
 * Множители коридора p10-p90 из бэктеста (intervals.json): для часа - по часу суток, для суток - по типу дня,
 * для месяца - одно значение. p10 = p50 × low, p90 = p50 × high.
 */
public final class Intervals {

	private final double[][] byHour;
	private final Map<DayKind, double[]> byDayKind;
	private final double[] month;

	public Intervals(double[][] byHour, Map<DayKind, double[]> byDayKind, double[] month) {
		if (byHour.length != ForecastGrid.HOURS || byDayKind.size() != DayKind.values().length || month.length != 2) {
			throw new IllegalArgumentException("в intervals.json нужны 24 часа, 3 типа дня и месяц");
		}
		this.byHour = new double[ForecastGrid.HOURS][];
		for (int h = 0; h < ForecastGrid.HOURS; h++) {
			this.byHour[h] = pair(byHour[h]);
		}
		this.byDayKind = new EnumMap<>(DayKind.class);
		byDayKind.forEach((kind, factors) -> this.byDayKind.put(kind, pair(factors)));
		this.month = pair(month);
	}

	public Band hour(int hour, double p50) {
		return Band.of(p50, byHour[hour]);
	}

	public Band day(DayKind kind, double p50) {
		return Band.of(p50, byDayKind.get(kind));
	}

	public Band month(double p50) {
		return Band.of(p50, month);
	}

	private static double[] pair(double[] factors) {
		if (factors.length != 2 || factors[0] > 1.0 || factors[1] < 1.0) {
			throw new IllegalArgumentException("множители коридора должны быть парой low <= 1 <= high");
		}
		return factors.clone();
	}

	/** Значение ряда с коридором. */
	public record Band(double p50, double p10, double p90) {

		static Band of(double p50, double[] factors) {
			return new Band(p50, p50 * factors[0], p50 * factors[1]);
		}

	}

}
