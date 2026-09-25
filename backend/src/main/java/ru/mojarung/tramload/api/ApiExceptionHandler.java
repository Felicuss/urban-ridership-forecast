package ru.mojarung.tramload.api;

import java.net.URI;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.ServerWebInputException;

import reactor.core.publisher.Mono;
import ru.mojarung.tramload.domain.ValidationException;

/**
 * Ошибки в формате Problem Details (RFC 9457). Нарушения области определения модели идут списком errors
 * с полем и текстом, внутренние ошибки - общим текстом без подробностей реализации.
 */
@RestControllerAdvice
public class ApiExceptionHandler extends ResponseEntityExceptionHandler {

	static final URI VALIDATION = URI.create("urn:tramload:problem:validation");
	static final URI INTERNAL = URI.create("urn:tramload:problem:internal");
	private static final Logger LOG = LoggerFactory.getLogger(ApiExceptionHandler.class);

	@ExceptionHandler(ValidationException.class)
	public Mono<ResponseEntity<ProblemDetail>> validation(ValidationException ex, ServerWebExchange exchange) {
		ProblemDetail problem = ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, ex.getMessage());
		problem.setType(VALIDATION);
		problem.setTitle("Запрос вне области определения модели");
		problem.setInstance(URI.create(exchange.getRequest().getPath().value()));
		List<Map<String, String>> errors = ex.violations().stream()
			.map(v -> Map.of("field", v.field(), "message", v.message()))
			.toList();
		problem.setProperty("errors", errors);
		return Mono.just(ResponseEntity.badRequest().body(problem));
	}

	@Override
	protected Mono<ResponseEntity<Object>> handleServerWebInputException(ServerWebInputException ex, HttpHeaders headers,
			HttpStatusCode status, ServerWebExchange exchange) {
		ex.getBody().setDetail("Параметр или тело запроса не разобраны: ожидается JSON по схеме /api/v1/openapi");
		return super.handleServerWebInputException(ex, headers, status, exchange);
	}

	@ExceptionHandler(RuntimeException.class)
	public Mono<ResponseEntity<ProblemDetail>> unexpected(RuntimeException ex, ServerWebExchange exchange) {
		LOG.error("необработанная ошибка на {}", exchange.getRequest().getPath(), ex);
		ProblemDetail problem = ProblemDetail.forStatusAndDetail(HttpStatus.INTERNAL_SERVER_ERROR,
				"Внутренняя ошибка сервиса, подробности в журнале");
		problem.setType(INTERNAL);
		problem.setTitle("Внутренняя ошибка");
		problem.setInstance(URI.create(exchange.getRequest().getPath().value()));
		return Mono.just(ResponseEntity.internalServerError().body(problem));
	}

}
