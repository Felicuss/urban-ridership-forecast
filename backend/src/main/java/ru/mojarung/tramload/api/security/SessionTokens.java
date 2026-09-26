package ru.mojarung.tramload.api.security;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.time.Instant;

import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.http.ResponseCookie;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

/**
 * Сессия интерфейса - JWT HS256 в HttpOnly-cookie. Подпись и проверку делает Spring Security (Nimbus),
 * срок жизни проверяет стандартный валидатор exp. Сервер ничего не хранит, поэтому сессия работает на любой
 * реплике за nginx, если у реплик один ключ.
 */
public final class SessionTokens {

	public static final String COOKIE = "chaspik_session";
	static final String ISSUER = "chaspik";
	static final String NAME_CLAIM = "name";

	private final JwtEncoder encoder;
	private final ReactiveJwtDecoder decoder;
	private final Duration ttl;

	public SessionTokens(SecretKey key, Duration ttl) {
		this.encoder = NimbusJwtEncoder.withSecretKey(key).algorithm(MacAlgorithm.HS256).build();
		this.decoder = NimbusReactiveJwtDecoder.withSecretKey(key).macAlgorithm(MacAlgorithm.HS256).build();
		this.ttl = ttl;
	}

	/**
	 * Ключ подписи: SHA-256 от AUTH_SECRET, а без него - от списка учётных записей. Во втором случае подделать
	 * сессию может только тот, кто и так знает пароли.
	 */
	public static SecretKey key(String secret, String users) {
		String material = secret.isBlank() ? "chaspik-session|" + users : secret;
		try {
			byte[] digest = MessageDigest.getInstance("SHA-256").digest(material.getBytes(StandardCharsets.UTF_8));
			return new SecretKeySpec(digest, "HmacSHA256");
		}
		catch (NoSuchAlgorithmException ex) {
			throw new IllegalStateException("в JVM нет SHA-256", ex);
		}
	}

	public String issue(String login, String name) {
		Instant now = Instant.now();
		JwtClaimsSet claims = JwtClaimsSet.builder()
			.issuer(ISSUER)
			.subject(login)
			.claim(NAME_CLAIM, name)
			.issuedAt(now)
			.expiresAt(now.plus(ttl))
			.build();
		JwsHeader header = JwsHeader.with(MacAlgorithm.HS256).build();
		return encoder.encode(JwtEncoderParameters.from(header, claims)).getTokenValue();
	}

	public ReactiveJwtDecoder decoder() {
		return decoder;
	}

	/** Cookie сессии: недоступна скриптам страницы и не уходит с чужих сайтов. */
	public ResponseCookie cookie(String token, boolean secure) {
		return ResponseCookie.from(COOKIE, token).httpOnly(true).secure(secure).sameSite("Strict").path("/")
			.maxAge(ttl).build();
	}

	public ResponseCookie clear(boolean secure) {
		return ResponseCookie.from(COOKIE, "").httpOnly(true).secure(secure).sameSite("Strict").path("/")
			.maxAge(Duration.ZERO).build();
	}

	public Duration ttl() {
		return ttl;
	}

}
