package ru.mojarung.tramload.api;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.WebTestClient;

import ru.mojarung.tramload.api.dto.AgentEventDto;

/** Контракт агента без ключа модели: статус честно говорит «не настроен», поток SSE и ошибки по RFC 9457. */
@SpringBootTest(properties = "tramload.agent.llm-api-key=")
@AutoConfigureWebTestClient
class AgentApiTest {

	@Autowired
	WebTestClient client;

	@Test
	void statusSaysTheAgentIsNotConfiguredWithoutAKey() {
		client.get().uri("/api/v1/agent/status").exchange()
			.expectStatus().isOk()
			.expectBody()
			.jsonPath("$.configured").isEqualTo(false)
			.jsonPath("$.memory").isEqualTo("memory");
	}

	@Test
	void chatStreamsAnErrorEventInsteadOfFailing() {
		List<ServerSentEvent<AgentEventDto>> events = client.post().uri("/api/v1/agent/chat")
			.contentType(MediaType.APPLICATION_JSON)
			.accept(MediaType.TEXT_EVENT_STREAM)
			.bodyValue("{\"session\":\"test-session-1\",\"message\":\"сколько на 17?\"}")
			.exchange()
			.expectStatus().isOk()
			.returnResult(new ParameterizedTypeReference<ServerSentEvent<AgentEventDto>>() {
			})
			.getResponseBody().collectList().block();

		assertThat(events).singleElement().satisfies(e -> {
			assertThat(e.event()).isEqualTo("error");
			assertThat(e.data().text()).contains("не настроен");
		});
	}

	@Test
	void badSessionIsAProblemDetail() {
		client.post().uri("/api/v1/agent/chat")
			.contentType(MediaType.APPLICATION_JSON)
			.bodyValue("{\"session\":\"x\",\"message\":\"вопрос\"}")
			.exchange()
			.expectStatus().isBadRequest()
			.expectBody().jsonPath("$.errors[0].field").isEqualTo("session");
	}

}
