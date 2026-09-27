package ru.mojarung.tramload.api;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

/** Лента сбоев без живого канала: архив 2025 года из артефактов и примерка сбоя на день прогноза. */
@SpringBootTest(properties = "tramload.news.live-url=")
@AutoConfigureWebTestClient
class NewsApiTest {

	@Autowired
	WebTestClient client;

	@Test
	void archiveIncidentsComeNewestFirstWithEventsInsideTheHorizon() {
		client.get().uri("/api/v1/news").exchange()
			.expectStatus().isOk()
			.expectBody()
			.jsonPath("$.incidents.length()").isEqualTo(31)
			.jsonPath("$.alpha").isEqualTo(0.5)
			.jsonPath("$.liveCheckedAt").doesNotExist()
			.jsonPath("$.incidents[0].id").isEqualTo("24410")
			.jsonPath("$.incidents[0].inForecast").isEqualTo(true)
			.jsonPath("$.incidents[0].events[0].route").isEqualTo(50)
			.jsonPath("$.incidents[30].id").isEqualTo("22183")
			.jsonPath("$.incidents[30].inForecast").isEqualTo(false)
			.jsonPath("$.incidents[30].events.length()").isEqualTo(0);
	}

	@Test
	void incidentCanBeTriedOnAnyForecastDay() {
		client.get().uri("/api/v1/news/23459/events?date=2025-11-14").exchange()
			.expectStatus().isOk()
			.expectBody()
			.jsonPath("$.length()").isEqualTo(2)
			.jsonPath("$[0].route").isEqualTo(12)
			.jsonPath("$[0].from").isEqualTo("2025-11-14")
			.jsonPath("$[0].hours").isEqualTo("10-10")
			.jsonPath("$[0].multiplier").isEqualTo(0.74)
			.jsonPath("$[0].label").isEqualTo("как сбой 08.11: технические причины");
	}

	@Test
	void dayAfterTheTimelineAndUnknownIncidentAreProblemDetails() {
		client.get().uri("/api/v1/news/23459/events?date=2026-11-01").exchange()
			.expectStatus().isBadRequest()
			.expectBody().jsonPath("$.errors[0].field").isEqualTo("date");
		client.get().uri("/api/v1/news/1/events?date=2025-11-14").exchange()
			.expectStatus().isBadRequest()
			.expectBody().jsonPath("$.errors[0].field").isEqualTo("id");
	}

}
