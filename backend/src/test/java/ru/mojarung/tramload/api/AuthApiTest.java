package ru.mojarung.tramload.api;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.WebTestClient;

import ru.mojarung.tramload.api.dto.UserDto;
import ru.mojarung.tramload.api.security.SessionTokens;

/** Вход диспетчера: без сессии API закрыт, cookie, Basic и Bearer открывают его, перебор паролей упирается в 429. */
@SpringBootTest(properties = { "tramload.auth.enabled=true",
		"tramload.auth.users=dispatcher:right-pass:Диспетчер смены,mcp:mcp-pass" })
@AutoConfigureWebTestClient
class AuthApiTest {

	@Autowired
	WebTestClient client;

	@Test
	void apiWithoutSessionIsAProblemWithoutBrowserLoginPrompt() {
		client.get().uri("/api/v1/meta").exchange()
			.expectStatus().isUnauthorized()
			.expectHeader().contentType(MediaType.APPLICATION_PROBLEM_JSON)
			.expectHeader().doesNotExist(HttpHeaders.WWW_AUTHENTICATE)
			.expectBody().jsonPath("$.title").isEqualTo("Нужен вход");
	}

	@Test
	void loginSetsAnHttpOnlyCookieThatOpensTheApi() {
		ResponseCookie cookie = login("dispatcher", "right-pass");

		assertThat(cookie.isHttpOnly()).isTrue();
		assertThat(cookie.getSameSite()).isEqualTo("Strict");
		client.get().uri("/api/v1/meta").cookie(SessionTokens.COOKIE, cookie.getValue()).exchange()
			.expectStatus().isOk();
		UserDto me = client.get().uri("/api/v1/auth/me").cookie(SessionTokens.COOKIE, cookie.getValue()).exchange()
			.expectStatus().isOk().expectBody(UserDto.class).returnResult().getResponseBody();
		assertThat(me).isEqualTo(new UserDto("dispatcher", "Диспетчер смены", true));
	}

	@Test
	void sameTokenWorksAsBearerForScripts() {
		String token = login("dispatcher", "right-pass").getValue();

		client.get().uri("/api/v1/meta").header(HttpHeaders.AUTHORIZATION, "Bearer " + token).exchange()
			.expectStatus().isOk();
	}

	@Test
	void mcpServerCanUseBasic() {
		client.get().uri("/api/v1/meta").headers(h -> h.setBasicAuth("mcp", "mcp-pass")).exchange()
			.expectStatus().isOk();
		client.get().uri("/api/v1/meta").headers(h -> h.setBasicAuth("mcp", "wrong")).exchange()
			.expectStatus().isUnauthorized();
	}

	@Test
	void wrongPasswordAndForgedTokenAreRejected() {
		client.post().uri("/api/v1/auth/login").bodyValue(Map.of("username", "dispatcher", "password", "nope")).exchange()
			.expectStatus().isUnauthorized()
			.expectBody().jsonPath("$.detail").isEqualTo("Неверный логин или пароль");
		String token = login("dispatcher", "right-pass").getValue();
		String forged = token.substring(0, token.lastIndexOf('.') + 1) + "AAAA";
		client.get().uri("/api/v1/meta").cookie(SessionTokens.COOKIE, forged).exchange()
			.expectStatus().isUnauthorized();
	}

	@Test
	void guessingIsLockedAfterTenWrongPasswords() {
		for (int i = 0; i < 10; i++) {
			client.post().uri("/api/v1/auth/login").bodyValue(Map.of("username", "mcp", "password", "guess" + i)).exchange()
				.expectStatus().isUnauthorized();
		}
		client.post().uri("/api/v1/auth/login").bodyValue(Map.of("username", "mcp", "password", "mcp-pass")).exchange()
			.expectStatus().isEqualTo(429);
	}

	@Test
	void healthAndApiDocsStayOpen() {
		client.get().uri("/actuator/health").exchange().expectStatus().isOk();
		client.get().uri("/api/v1/openapi").exchange().expectStatus().isOk();
	}

	@Test
	void logoutClearsTheCookie() {
		ResponseCookie cleared = client.post().uri("/api/v1/auth/logout").exchange()
			.expectStatus().isNoContent()
			.returnResult(Void.class).getResponseCookies().getFirst(SessionTokens.COOKIE);

		assertThat(cleared).isNotNull();
		assertThat(cleared.getMaxAge()).isZero();
	}

	private ResponseCookie login(String username, String password) {
		ResponseCookie cookie = client.post().uri("/api/v1/auth/login")
			.bodyValue(Map.of("username", username, "password", password)).exchange()
			.expectStatus().isOk()
			.returnResult(UserDto.class).getResponseCookies().getFirst(SessionTokens.COOKIE);
		assertThat(cookie).isNotNull();
		return cookie;
	}

}
