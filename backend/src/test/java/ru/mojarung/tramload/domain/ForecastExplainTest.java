package ru.mojarung.tramload.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

import ru.mojarung.tramload.TestArtifacts;

/** Водопад «из чего сложился прогноз»: последний шаг равен прогнозу сервиса, каждый шаг меняет только свой фактор. */
class ForecastExplainTest {

	private static final ForecastModel MODEL = TestArtifacts.model();
	private static final ForecastEngine ENGINE = new ForecastEngine(MODEL.components(), MODEL.constants());
	private static final Scenario DEFAULT = Scenario.of(MODEL.catalog().defaults());

	@Test
	void lastStepIsTheForecastForRouteAndNetwork() {
		double[] prediction = ENGINE.compute(DEFAULT);
		LocalDate date = LocalDate.parse("2025-12-31");
		ForecastGrid grid = MODEL.grid();
		double network = 0;
		for (int route : grid.routes()) {
			double day = 0;
			for (int h = 0; h < ForecastGrid.HOURS; h++) {
				day += prediction[grid.cell(grid.routeIndex(route), grid.dayIndex(date), h)];
			}
			double[] steps = ENGINE.explain(DEFAULT, route, date).totals();
			assertThat(steps[steps.length - 1]).as("маршрут %d", route).isCloseTo(day, within(1e-6));
			network += day;
		}
		double[] all = ENGINE.explain(DEFAULT, null, date).totals();
		assertThat(all[all.length - 1]).isCloseTo(network, within(1e-6));
	}

	@Test
	void monthLevelSliderMovesOnlyItsStep() {
		LocalDate date = LocalDate.parse("2025-11-18");
		double[] base = ENGINE.explain(DEFAULT, 17, date).totals();
		Scenario higher = Scenario.of(MODEL.catalog().resolve(Map.of("level_nov", 1.1)));
		double[] moved = ENGINE.explain(higher, 17, date).totals();

		assertThat(moved[0]).isEqualTo(base[0]);
		assertThat(moved[1] / moved[0]).isCloseTo(1.1, within(1e-9));
		assertThat(List.of(moved[1] > base[1], moved[6] > base[6])).containsOnly(true);
	}

}
