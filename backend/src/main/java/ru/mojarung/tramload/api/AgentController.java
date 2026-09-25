package ru.mojarung.tramload.api;

import java.util.regex.Pattern;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import reactor.core.publisher.Flux;
import ru.mojarung.tramload.api.dto.AgentChatRequest;
import ru.mojarung.tramload.api.dto.AgentEventDto;
import ru.mojarung.tramload.api.dto.AgentResetRequest;
import ru.mojarung.tramload.api.dto.AgentStatusDto;
import ru.mojarung.tramload.application.AgentService;
import ru.mojarung.tramload.domain.ValidationException;

/** Агент диспетчера: вопрос словами, ответ потоком событий SSE (шаги, команды интерфейсу, ответ). */
@RestController
@RequestMapping("/api/v1/agent")
@Tag(name = "Агент", description = "Помощник диспетчера на модели Ollama Cloud с инструментами MCP-сервера")
public class AgentController {

	private static final Pattern SESSION = Pattern.compile("[A-Za-z0-9_-]{8,64}");

	private final AgentService agent;

	public AgentController(AgentService agent) {
		this.agent = agent;
	}

	@PostMapping(path = "/chat", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
	@Operation(summary = "Вопрос агенту",
			description = "Поток событий: step - вызван инструмент, ui - команда интерфейсу, answer - ответ, error - "
					+ "почему ответа нет. История диалога хранится по session сутки.")
	public Flux<ServerSentEvent<AgentEventDto>> chat(@RequestBody AgentChatRequest request) {
		session(request.session());
		if (request.message() == null) {
			throw ValidationException.of("message", "нужен текст вопроса");
		}
		return agent.turn(request.session(), request.message(), request.context())
			.map(e -> ServerSentEvent.builder(AgentEventDto.of(e)).event(e.type().name().toLowerCase()).build());
	}

	@PostMapping("/reset")
	@Operation(summary = "Начать диалог заново")
	public ResponseEntity<Void> reset(@RequestBody AgentResetRequest request) {
		agent.reset(session(request.session()));
		return ResponseEntity.noContent().build();
	}

	@GetMapping("/status")
	@Operation(summary = "Настроен ли агент и где его память")
	public AgentStatusDto status() {
		AgentService.Status s = agent.status();
		return new AgentStatusDto(s.configured(), s.model(), s.memory(), s.memoryHealthy());
	}

	private static String session(String session) {
		if (session == null || !SESSION.matcher(session).matches()) {
			throw ValidationException.of("session", "8-64 символа: латиница, цифры, - и _");
		}
		return session;
	}

}
