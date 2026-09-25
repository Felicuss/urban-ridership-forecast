package ru.mojarung.tramload.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;

import ru.mojarung.tramload.TestArtifacts;
import ru.mojarung.tramload.domain.network.Stop;

/** Часы складываются в сутки и месяцы без потерь, остановки складываются в маршрут и сеть. */
class AggregationConsistencyTest {

	private static final ForecastModel MODEL = TestArtifacts.model();
	private static final Aggregator AGGREGATOR = new Aggregator(MODEL.timeline(), MODEL.intervals());
	private static final double[] PREDICTION = new ForecastEngine(MODEL.components(), MODEL.constants())
		.compute(Scenario.of(MODEL.catalog().defaults()));
	private static final LocalDate FROM = MODEL.grid().start();
	private static final LocalDate TO = MODEL.grid().end();

	@Test
	void hoursDaysAndMonthsGiveTheSameTotal() {
		Map<Integer, Double> route17 = Map.of(17, 1.0);

		double hours = total(route17, Granularity.HOUR);
		double days = total(route17, Granularity.DAY);
		List<Aggregator.Point> months = AGGREGATOR.series(PREDICTION, route17, FROM, TO, HourWindow.ALL_DAY,
				Granularity.MONTH);

		assertThat(months).extracting(Aggregator.Point::period).containsExactly("2025-11", "2025-12");
		assertThat(days).isCloseTo(hours, within(1e-6));
		assertThat(Aggregator.total(months).p50()).isCloseTo(hours, within(1e-6));
		assertThat(hours).isCloseTo(sumOfCells(17), within(1e-6));
	}

	@Test
	void stopsAddUpToTheWholeNetwork() {
		Map<Integer, Double> network = MODEL.grid().routes().stream()
			.collect(Collectors.toMap(Function.identity(), r -> 1.0));
		double viaStops = MODEL.network().stops().stream()
			.map(Stop::id)
			.mapToDouble(id -> total(MODEL.network().stopWeights(id), Granularity.DAY))
			.sum();

		assertThat(viaStops).isCloseTo(total(network, Granularity.DAY), within(1e-3));
	}

	@Test
	void wholeLineSegmentEqualsTheDirectionHalfOfTheRoute() {
		var line = MODEL.network().routeStops(17).stream().filter(rs -> rs.direction() == 0).toList();
		Map<Integer, Double> segment = MODEL.network().segmentWeights(17, 0, line.getFirst().stopId(),
				line.getLast().stopId());

		assertThat(segment.get(17)).isCloseTo(0.5, within(1e-12));
	}

	private static double total(Map<Integer, Double> weights, Granularity granularity) {
		return Aggregator.total(AGGREGATOR.series(PREDICTION, weights, FROM, TO, HourWindow.ALL_DAY, granularity)).p50();
	}

	private static double sumOfCells(int route) {
		ForecastGrid g = MODEL.grid();
		double sum = 0;
		for (int d = 0; d < g.days(); d++) {
			for (int h = 0; h < ForecastGrid.HOURS; h++) {
				sum += PREDICTION[g.cell(g.routeIndex(route), d, h)];
			}
		}
		return sum;
	}

}
