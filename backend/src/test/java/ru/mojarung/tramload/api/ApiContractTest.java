package ru.mojarung.tramload.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

import java.io.IOException;
import java.nio.file.Files;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import ru.mojarung.tramload.TestArtifacts;
import ru.mojarung.tramload.api.dto.ForecastResponse;
import ru.mojarung.tramload.api.dto.NetworkLoadResponse;
import ru.mojarung.tramload.api.dto.PointDto;
import ru.mojarung.tramload.api.dto.ScenarioPointDto;
import ru.mojarung.tramload.api.dto.ScenarioResponse;

/** Контракт API для фронта: параметры, коды ответов и ошибки в формате RFC 9457. */
@SpringBootTest
@AutoConfigureWebTestClient
class ApiContractTest {

	@Autowired
	WebTestClient client;

	@Test
	void dayHorizonGivesHourlySeriesThatMatchesTheSubmission() throws IOException {
		ForecastResponse r = get("/api/v1/forecast?level=route&id=17&horizon=day&from=2025-11-03", ForecastResponse.class);

		assertThat(r.points()).hasSize(24);
		assertThat(r.points()).allSatisfy(p -> assertThat(p.p10()).isLessThanOrEqualTo(p.p50()));
		assertThat(r.points()).allSatisfy(p -> assertThat(p.p90()).isGreaterThanOrEqualTo(p.p50()));
		assertThat(r.total().p50()).isCloseTo(r.points().stream().mapToDouble(PointDto::p50).sum(), within(1.5));
		assertThat(r.points().get(8).p50()).isCloseTo(submission("17;2025-11-03;8;"), within(0.5));
	}

	@Test
	void weekHorizonGivesSevenDaysWithTheirPeakHour() {
		ForecastResponse week = get("/api/v1/forecast?level=route&id=17&horizon=week&from=2025-11-10", ForecastResponse.class);
		ForecastResponse day = get("/api/v1/forecast?level=route&id=17&horizon=day&from=2025-11-14", ForecastResponse.class);

		assertThat(week.granularity()).isEqualTo("day");
		assertThat(week.points()).extracting(PointDto::period).hasSize(7).startsWith("2025-11-10").endsWith("2025-11-16");
		PointDto friday = week.points().get(4);
		PointDto busiest = day.points().stream().max((a, b) -> Double.compare(a.p50(), b.p50())).orElseThrow();
		assertThat(friday.peakAt()).isEqualTo(busiest.period());
		assertThat(friday.peak()).isCloseTo(busiest.p50(), within(0.1));
		assertThat(day.points()).allSatisfy(p -> assertThat(p.peak()).isNull());
		assertThat(week.total().peak()).isEqualTo(week.points().stream().mapToDouble(PointDto::peak).max().orElseThrow());
	}

	@Test
	void yearHorizonCoversNovember2025ToOctober2026() {
		ForecastResponse r = get("/api/v1/forecast?level=network&horizon=year", ForecastResponse.class);

		assertThat(r.points()).extracting(PointDto::period).hasSize(12).startsWith("2025-11").endsWith("2026-10");
		assertThat(r.to()).hasToString("2026-10-31");
		assertThat(r.notes()).isNotEmpty();
	}

	@ParameterizedTest
	@CsvSource(delimiter = '|', value = {
			"level=route&id=99|id",
			"level=route&id=17&from=2027-01-05|from",
			"level=route&id=17&horizon=month&from=2024-10-10|from",
			"level=route&id=17&from=2025-11-10&to=2025-11-05|to",
			"level=route&id=17&horizon=decade|horizon",
			"level=network&horizon=year&granularity=hour|granularity",
			"level=route&id=17&hours=20-7|hours",
			"level=stop&id=nope|id",
			"id=17|level" })
	void invalidQueryIsAProblemDetailNamingTheField(String query, String field) {
		client.get().uri("/api/v1/forecast?" + query).exchange()
			.expectStatus().isBadRequest()
			.expectHeader().contentType(MediaType.APPLICATION_PROBLEM_JSON)
			.expectBody()
			.jsonPath("$.type").isEqualTo("urn:tramload:problem:validation")
			.jsonPath("$.status").isEqualTo(400)
			.jsonPath("$.instance").isEqualTo("/api/v1/forecast")
			.jsonPath("$.errors[0].field").isEqualTo(field);
	}

	@Test
	void allViolationsAreReportedAtOnce() {
		client.get().uri("/api/v1/forecast?level=route&id=99&from=2027-01-05").exchange()
			.expectStatus().isBadRequest()
			.expectBody().jsonPath("$.errors.length()").isEqualTo(2);
	}

	@ParameterizedTest
	@CsvSource(delimiter = '|', value = {
			"{\"level_nov\": 1.5}|coefficients.level_nov",
			"{\"no_such_slider\": 1}|coefficients.no_such_slider",
			"{\"weekend_restore_date\": \"15.11.2025\"}|coefficients.weekend_restore_date",
			"{\"dec31_free_from_hour\": 20.5}|coefficients.dec31_free_from_hour" })
	void coefficientOutsideCatalogIsRejected(String coefficients, String field) {
		String body = "{\"query\": {\"level\": \"route\", \"id\": \"17\"}, \"coefficients\": " + coefficients + "}";
		postScenario(body).expectStatus().isBadRequest()
			.expectHeader().contentType(MediaType.APPLICATION_PROBLEM_JSON)
			.expectBody().jsonPath("$.errors[0].field").isEqualTo(field);
	}

	@Test
	void scenarioChangesOnlyWhatTheSliderControls() {
		String body = """
				{"query": {"level": "route", "id": "17", "from": "2025-11-28", "to": "2025-12-02", "granularity": "day"},
				 "coefficients": {"level_dec": 1.1}}""";
		ScenarioResponse r = postScenario(body).expectStatus().isOk().expectBody(ScenarioResponse.class).returnResult()
			.getResponseBody();

		assertThat(r.coefficients()).containsEntry("level_dec", 1.1);
		Map<String, ScenarioPointDto> byDay = r.points().stream()
			.collect(java.util.stream.Collectors.toMap(ScenarioPointDto::period, p -> p));
		assertThat(byDay.get("2025-11-28").delta()).isZero();
		assertThat(byDay.get("2025-12-01").deltaPct()).isCloseTo(100 * (1.1 / 1.0339 - 1), within(0.2));
	}

	@Test
	void closureEventZeroesTheRouteInItsHours() {
		String body = """
				{"query": {"level": "route", "id": "50", "horizon": "day", "from": "2025-11-22"},
				 "events": [{"route": 50, "from": "2025-11-22", "to": "2025-11-22", "hours": "10-18", "multiplier": 0}]}""";
		ScenarioResponse r = postScenario(body).expectStatus().isOk().expectBody(ScenarioResponse.class).returnResult()
			.getResponseBody();

		assertThat(r.points().subList(10, 19)).allSatisfy(p -> assertThat(p.p50()).isZero());
		assertThat(r.points().get(9).p50()).isEqualTo(r.points().get(9).baseline()).isPositive();
	}

	@Test
	void eventScalesTheOutlookDayOf2026() {
		String body = """
				{"query": {"level": "route", "id": "17", "horizon": "day", "from": "2026-09-27"},
				 "events": [{"from": "2026-09-27", "to": "2026-09-27", "multiplier": 0.85, "label": "снегопад"}]}""";
		ScenarioResponse r = postScenario(body).expectStatus().isOk().expectBody(ScenarioResponse.class).returnResult()
			.getResponseBody();

		assertThat(r.points()).allSatisfy(p -> assertThat(p.p50()).isCloseTo(0.85 * p.baseline(), within(0.06)));
		assertThat(r.total().baseline()).isPositive();
	}

	@Test
	void eventAfterTheTimelineIsRejected() {
		String body = """
				{"query": {"level": "route", "id": "17"},
				 "events": [{"from": "2026-10-31", "to": "2026-11-01", "multiplier": 0.85}]}""";
		postScenario(body).expectStatus().isBadRequest()
			.expectBody().jsonPath("$.errors[0].field").isEqualTo("events[0]");
	}

	@Test
	void networkGeoJsonIsCachedByEtag() {
		String etag = client.get().uri("/api/v1/network").exchange()
			.expectStatus().isOk()
			.expectHeader().contentType("application/geo+json")
			.returnResult(byte[].class).getResponseHeaders().getETag();

		client.get().uri("/api/v1/network").header("If-None-Match", etag).exchange().expectStatus().isNotModified();
	}

	@Test
	void anyDateOfTheTimelineHasItsSourceAndCorridor() {
		ForecastResponse fact = get("/api/v1/forecast?level=route&id=17&horizon=day&from=2025-06-10", ForecastResponse.class);
		ForecastResponse outlook = get("/api/v1/forecast?level=network&horizon=month&from=2026-03-01", ForecastResponse.class);
		NetworkLoadResponse load = get("/api/v1/network/load?date=2025-06-10", NetworkLoadResponse.class);

		assertThat(fact.points()).hasSize(24).allSatisfy(p -> {
			assertThat(p.source()).isEqualTo("fact");
			assertThat(p.p10()).isEqualTo(p.p50()).isEqualTo(p.p90());
		});
		assertThat(outlook.points()).hasSize(31).allSatisfy(p -> {
			assertThat(p.source()).isEqualTo("outlook");
			assertThat(p.p90()).isCloseTo(p.p50() * 1.12, within(0.2));
		});
		assertThat(load.source()).isEqualTo("fact");
		assertThat(fact.notes()).anySatisfy(n -> assertThat(n).contains("факт"));
	}

	@Test
	void calendarCoversTheWholeTimeline() {
		client.get().uri("/api/v1/calendar").exchange()
			.expectStatus().isOk()
			.expectBody()
			.jsonPath("$.length()").isEqualTo(669)
			.jsonPath("$[0].date").isEqualTo("2025-01-01")
			.jsonPath("$[0].source").isEqualTo("fact")
			.jsonPath("$[668].date").isEqualTo("2026-10-31")
			.jsonPath("$[668].source").isEqualTo("outlook");
	}

	@Test
	void factorsCarryEveryExternalSourceTheUiShows() {
		client.get().uri("/api/v1/factors").exchange()
			.expectStatus().isOk()
			.expectHeader().contentType(MediaType.APPLICATION_JSON)
			.expectBody()
			.jsonPath("$.calendar.length()").isEqualTo(61)
			.jsonPath("$.weather.temp.length()").isEqualTo(61)
			.jsonPath("$.weather.temp[0].length()").isEqualTo(24)
			.jsonPath("$.schedule.routes.17.weekday.headway_min.length()").isEqualTo(24)
			.jsonPath("$.history.routes.17.length()").isEqualTo(304)
			.jsonPath("$.traffic.source").exists()
			.jsonPath("$.city_ridership.per_day").isArray()
			.jsonPath("$.events").isArray();
	}

	@Test
	void heatmapFramesCoverEveryRouteAndStop() {
		NetworkLoadResponse r = get("/api/v1/network/load?date=2025-11-03&hours=7-9", NetworkLoadResponse.class);

		assertThat(r.hours()).containsExactly(7, 8, 9);
		assertThat(r.routes()).hasSize(TestArtifacts.model().grid().routes().size());
		assertThat(r.stops()).hasSize(TestArtifacts.model().network().stops().size());
		assertThat(r.stops()).allSatisfy(s -> assertThat(s.values()).hasSize(3));
	}

	@Test
	void unknownPathIsAProblemDetailToo() {
		client.get().uri("/api/v1/nope").exchange()
			.expectStatus().isNotFound()
			.expectHeader().contentType(MediaType.APPLICATION_PROBLEM_JSON);
	}

	@Test
	void pastDaysCarryThePlanMadeTheEveningBefore() throws IOException {
		ForecastResponse day = get("/api/v1/forecast?level=route&id=17&horizon=day&from=2025-10-15", ForecastResponse.class);
		ForecastResponse week = get("/api/v1/forecast?level=route&id=17&horizon=week&from=2025-10-13", ForecastResponse.class);
		ForecastResponse network = get("/api/v1/forecast?level=network&horizon=day&from=2025-10-15", ForecastResponse.class);
		ForecastResponse forecast = get("/api/v1/forecast?level=route&id=17&horizon=day&from=2025-11-15",
				ForecastResponse.class);
		ForecastResponse january = get("/api/v1/forecast?level=route&id=17&horizon=day&from=2025-01-15",
				ForecastResponse.class);

		assertThat(day.points()).allSatisfy(p -> assertThat(p.plan()).isNotNull());
		assertThat(day.points().get(8).plan()).isCloseTo(plan("17,2025-10-15,8,"), within(0.05));
		double hourly = day.points().stream().mapToDouble(PointDto::plan).sum();
		assertThat(day.total().plan()).isCloseTo(hourly, within(1.0));
		assertThat(week.points().get(2).plan()).isCloseTo(hourly, within(1.0));
		assertThat(network.total().plan()).isGreaterThan(day.total().plan());
		assertThat(forecast.points()).allSatisfy(p -> assertThat(p.plan()).isNull());
		assertThat(forecast.total().plan()).isNull();
		assertThat(january.points()).allSatisfy(p -> assertThat(p.plan()).isNull());
	}

	private <T> T get(String uri, Class<T> type) {
		return client.get().uri(uri).exchange().expectStatus().isOk().expectBody(type).returnResult().getResponseBody();
	}

	private WebTestClient.ResponseSpec postScenario(String body) {
		return client.post().uri("/api/v1/forecast/scenario").contentType(MediaType.APPLICATION_JSON).bodyValue(body)
			.exchange();
	}

	private static double plan(String prefix) throws IOException {
		String line = Files.readAllLines(TestArtifacts.dir().resolve("plan.csv")).stream()
			.filter(l -> l.startsWith(prefix)).findFirst().orElseThrow();
		return Double.parseDouble(line.substring(prefix.length()));
	}

	private static double submission(String prefix) throws IOException {
		List<String> lines = Files.readAllLines(TestArtifacts.repoRoot().resolve(TestArtifacts.model().info()
			.defaultSubmission()));
		String line = lines.stream().filter(l -> l.startsWith(prefix)).findFirst().orElseThrow();
		return Double.parseDouble(line.substring(prefix.length()));
	}

}
