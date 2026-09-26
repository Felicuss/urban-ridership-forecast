package ru.mojarung.tramload.api.security;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Вход в сервис. users - учётные записи «логин:пароль:имя» через запятую, secret - ключ подписи сессии,
 * общий для всех реплик за nginx; без него ключ выводится из users, и реплики с одним окружением его совпадают.
 */
@ConfigurationProperties("tramload.auth")
public record AuthProperties(boolean enabled, String users, String secret, Duration sessionTtl) {

	private static final Duration DEFAULT_TTL = Duration.ofHours(12);

	public AuthProperties {
		users = users == null ? "" : users;
		secret = secret == null ? "" : secret;
		sessionTtl = sessionTtl == null ? DEFAULT_TTL : sessionTtl;
	}

}
