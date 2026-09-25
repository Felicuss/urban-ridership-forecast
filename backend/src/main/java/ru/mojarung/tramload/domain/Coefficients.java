package ru.mojarung.tramload.domain;

import java.time.LocalDate;
import java.time.LocalDateTime;

/**
 * Значения ползунков для одного расчёта. Ключи и диапазоны описаны в coefficients.json,
 * смысл каждого - в artifacts/README.md и analysis/s10_forecast.py (Coefficients).
 */
public record Coefficients(
		double levelNov,
		double levelDec,
		double trafficWeight,
		double holidayToSunday,
		double workingSaturday,
		double lastWorkdaysDec,
		double dec31Day,
		int dec31FreeFromHour,
		LocalDate weekendRestoreDate,
		LocalDate t1Start,
		double t1Route7,
		boolean route5On,
		LocalDateTime route5Start,
		double route5Workday,
		boolean weather,
		double precipDayCoef,
		double hourPrecipCoef,
		double frostCoef) {
}
