package ru.mojarung.tramload.api.security;

import java.nio.charset.StandardCharsets;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

/**
 * 401 в формате Problem Details без заголовка WWW-Authenticate: Basic, иначе браузер показал бы своё окно
 * логина поверх интерфейса. Интерфейс по 401 сам открывает экран входа.
 */
final class ProblemEntryPoint implements ServerAuthenticationEntryPoint {

	static final String BODY = """
			{"type":"urn:tramload:problem:unauthorized","title":"Нужен вход","status":401,\
			"detail":"Войдите в «Час пик»: сессии нет или она истекла"}""";

	@Override
	public Mono<Void> commence(ServerWebExchange exchange, AuthenticationException ex) {
		ServerHttpResponse response = exchange.getResponse();
		response.setStatusCode(HttpStatus.UNAUTHORIZED);
		response.getHeaders().setContentType(MediaType.APPLICATION_PROBLEM_JSON);
		DataBuffer body = response.bufferFactory().wrap(BODY.getBytes(StandardCharsets.UTF_8));
		return response.writeWith(Mono.just(body));
	}

}
