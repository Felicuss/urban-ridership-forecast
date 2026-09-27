package ru.mojarung.tramload.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

import java.io.IOException;
import java.nio.file.Files;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;

import ru.mojarung.tramload.TestArtifacts;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * Шкала времени: факт - это данные организаторов без проверок оборудования в нерабочие часы, оценка 2026
 * сходится с годовым прогнозом, сценарий их не трогает.
 */
class TimelineTest {

	private static final ForecastModel MODEL = TestArtifacts.model();
	private static final Timeline TIMELINE = MODEL.timeline();
	private static final ForecastEngine ENGINE = new ForecastEngine(MODEL.components(), MODEL.constants());
	private static final double[] DEFAULT = ENGINE.compute(Scenario.of(MODEL.catalog().defaults()));

	@Test
	void calendar2027IncludesWorkingSaturdayAndTransfers() {
		assertThat(TIMELINE.end()).isEqualTo(LocalDate.of(2027, 12, 31));
		assertThat(TIMELINE.day(TIMELINE.dayIndex(LocalDate.of(2027, 2, 20))).dayOff()).isFalse();
		for (LocalDate date : List.of(LocalDate.of(2027, 2, 22), LocalDate.of(2027, 5, 3),
				LocalDate.of(2027, 5, 10), LocalDate.of(2027, 6, 14), LocalDate.of(2027, 11, 5), LocalDate.of(2027, 12, 31))) {
			assertThat(TIMELINE.day(TIMELINE.dayIndex(date)).dayOff()).as(date.toString()).isTrue();
		}
	}

	@Test
	void factIsTheOrganizersHourlyLabelsWithoutEquipmentChecks() throws IOException {
		List<String> lines = Files.readAllLines(TestArtifacts.repoRoot().resolve("dataset/labels/labels_day_test.csv"));
		JsonNode checks = JsonMapper.builder().build()
			.readTree(TestArtifacts.dir().resolve("factors.json").toFile())
			.path("equipment_checks");

		for (String line : lines.subList(1, lines.size())) {
			String[] f = line.split(";");
			int route = Integer.parseInt(f[0]);
			int hour = Integer.parseInt(f[2]);
			Set<Integer> off = checks.path("off_hours").path(f[0]).valueStream().map(JsonNode::asInt)
				.collect(Collectors.toSet());
			double value = TIMELINE.value(TIMELINE.routeIndex(route), TIMELINE.dayIndex(LocalDate.parse(f[1])), hour, DEFAULT);
			assertThat(value).as(line).isEqualTo(off.contains(hour) ? 0.0 : Double.parseDouble(f[3]));
		}
		assertThat(checks.path("validations").asInt()).isPositive();
		assertThat(TIMELINE.day(TIMELINE.dayIndex(LocalDate.of(2025, 10, 31))).source()).isEqualTo(Source.FACT);
	}

	@Test
	void outlookMonthsAddUpToTheYearForecast() {
		for (YearForecast.Row row : MODEL.year().rows()) {
			if (!"seasonal_index".equals(row.method())) {
				continue;
			}
			YearMonth month = row.month();
			double sum = 0;
			for (LocalDate d = month.atDay(1); !d.isAfter(month.atEndOfMonth()); d = d.plusDays(1)) {
				sum += TIMELINE.daySum(TIMELINE.routeIndex(row.route()), TIMELINE.dayIndex(d), DEFAULT);
			}
			assertThat(sum).as("маршрут %d, %s", row.route(), month).isCloseTo(row.p50(), within(row.p50() * 0.002 + 1));
		}
	}

	@Test
	void scenarioChangesOnlyTheForecastDays() {
		double[] shifted = ENGINE.compute(Scenario.of(MODEL.catalog().resolve(Map.of("level_nov", 1.1))));
		int route = TIMELINE.routeIndex(17);
		int fact = TIMELINE.dayIndex(LocalDate.of(2025, 10, 14));
		int forecast = TIMELINE.dayIndex(LocalDate.of(2025, 11, 11));
		int outlook = TIMELINE.dayIndex(LocalDate.of(2026, 3, 11));

		assertThat(TIMELINE.daySum(route, fact, shifted)).isEqualTo(TIMELINE.daySum(route, fact, DEFAULT)).isPositive();
		assertThat(TIMELINE.daySum(route, outlook, shifted)).isEqualTo(TIMELINE.daySum(route, outlook, DEFAULT)).isPositive();
		assertThat(TIMELINE.daySum(route, forecast, shifted) / TIMELINE.daySum(route, forecast, DEFAULT))
			.isCloseTo(1.1 / 1.0027, within(1e-9));
	}

	@Test
	void officialCalendarTransfersReachTheTimeline() {
		DayInfo friday = TIMELINE.day(TIMELINE.dayIndex(LocalDate.of(2026, 1, 9)));
		DayInfo saturday = TIMELINE.day(TIMELINE.dayIndex(LocalDate.of(2025, 11, 1)));

		assertThat(friday.dayOff()).isTrue();
		assertThat(friday.kind()).isEqualTo(DayKind.SUNDAY);
		assertThat(saturday.dayOff()).isFalse();
		assertThat(saturday.kind()).isEqualTo(DayKind.WORKDAY);
	}

}
