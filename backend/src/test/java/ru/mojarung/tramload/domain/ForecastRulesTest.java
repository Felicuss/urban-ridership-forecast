package ru.mojarung.tramload.domain;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import ru.mojarung.tramload.TestArtifacts;

/** Правила событий, которые дали баллы на лидерборде: их поломка не видна по сумме прогноза. */
class ForecastRulesTest {

	private static final ForecastModel MODEL = TestArtifacts.model();
	private static final ForecastEngine ENGINE = new ForecastEngine(MODEL.components(), MODEL.constants());
	private static final double[] DEFAULT = ENGINE.compute(Scenario.of(MODEL.catalog().defaults()));
	private static final LocalDate NEW_YEAR_EVE = LocalDate.of(2025, 12, 31);

	@Test
	void newYearEveIsFreeFromEightPmOnEveryRoute() {
		for (int route : MODEL.grid().routes()) {
			for (int hour = 20; hour < 24; hour++) {
				assertThat(value(DEFAULT, route, NEW_YEAR_EVE, hour)).as("маршрут %d, %d:00", route, hour).isZero();
			}
		}
		assertThat(value(DEFAULT, 17, NEW_YEAR_EVE, 19)).isPositive();
	}

	@Test
	void route5CarriesPassengersOnlyAfterLaunchOnDecember16At18() {
		LocalDate launch = LocalDate.of(2025, 12, 16);
		for (LocalDate d = MODEL.grid().start(); d.isBefore(launch); d = d.plusDays(1)) {
			assertThat(daySum(DEFAULT, 5, d)).as("маршрут 5, %s", d).isZero();
		}
		assertThat(value(DEFAULT, 5, launch, 17)).isZero();
		assertThat(value(DEFAULT, 5, launch, 18)).isPositive();
		assertThat(daySum(DEFAULT, 5, LocalDate.of(2025, 12, 17))).isPositive();
	}

	@ParameterizedTest
	@ValueSource(ints = { 7, 50 })
	void weekendsOfRoutes7And50ReturnToFullLineOnNovember15(int route) {
		double saturdayBefore = daySum(DEFAULT, route, LocalDate.of(2025, 11, 8));
		double saturdayAfter = daySum(DEFAULT, route, LocalDate.of(2025, 11, 15));
		double workday = daySum(DEFAULT, route, LocalDate.of(2025, 11, 10));

		assertThat(saturdayAfter).isGreaterThan(saturdayBefore * 1.3).isLessThan(workday);
	}

	@Test
	void restoreDateSliderMovesTheWeekendJump() {
		LocalDate saturday = LocalDate.of(2025, 11, 8);
		double[] early = ENGINE.compute(Scenario.of(MODEL.catalog().resolve(Map.of("weekend_restore_date", "2025-11-08"))));

		assertThat(daySum(early, 50, saturday)).isGreaterThan(daySum(DEFAULT, 50, saturday) * 5);
		assertThat(daySum(early, 50, LocalDate.of(2025, 11, 15))).isEqualTo(daySum(DEFAULT, 50, LocalDate.of(2025, 11, 15)));
	}

	private static double value(double[] prediction, int route, LocalDate date, int hour) {
		ForecastGrid g = MODEL.grid();
		return prediction[g.cell(g.routeIndex(route), g.dayIndex(date), hour)];
	}

	private static double daySum(double[] prediction, int route, LocalDate date) {
		double sum = 0;
		for (int h = 0; h < ForecastGrid.HOURS; h++) {
			sum += value(prediction, route, date, h);
		}
		return sum;
	}

}
