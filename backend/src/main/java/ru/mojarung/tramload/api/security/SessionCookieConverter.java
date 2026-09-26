package ru.mojarung.tramload.api.security;

import org.springframework.http.HttpCookie;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.web.server.authentication.ServerBearerTokenAuthenticationConverter;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

/**
 * Токен сессии: сначала из cookie интерфейса, иначе из заголовка Authorization: Bearer (замер k6, скрипты).
 * Запрос без токена идёт дальше к входу по логину и паролю (Basic) или получает 401.
 */
final class SessionCookieConverter implements ServerAuthenticationConverter {

	private final ServerBearerTokenAuthenticationConverter header = new ServerBearerTokenAuthenticationConverter();

	@Override
	public Mono<Authentication> convert(ServerWebExchange exchange) {
		HttpCookie cookie = exchange.getRequest().getCookies().getFirst(SessionTokens.COOKIE);
		if (cookie != null && !cookie.getValue().isBlank()) {
			return Mono.just(new BearerTokenAuthenticationToken(cookie.getValue()));
		}
		return header.convert(exchange);
	}

}
