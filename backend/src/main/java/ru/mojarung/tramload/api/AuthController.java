package ru.mojarung.tramload.api;

import java.net.URI;
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import reactor.core.publisher.Mono;
import ru.mojarung.tramload.api.dto.LoginRequest;
import ru.mojarung.tramload.api.dto.UserDto;
import ru.mojarung.tramload.api.security.Accounts;
import ru.mojarung.tramload.api.security.AuthProperties;
import ru.mojarung.tramload.api.security.SessionTokens;

/**
 * Вход диспетчера: логин и пароль в обмен на сессию в HttpOnly-cookie, выход и текущий пользователь.
 * После 10 неверных паролей подряд логин закрывается на 10 минут, чтобы пароль нельзя было перебрать.
 */
@RestController
@RequestMapping("/api/v1/auth")
@Tag(name = "Вход", description = "Сессия диспетчера")
public class AuthController {

	static final URI AUTH = URI.create("urn:tramload:problem:auth");
	private static final int MAX_FAILURES = 10;
	private static final Duration LOCKOUT = Duration.ofMinutes(10);
	private static final UserDto GUEST = new UserDto("guest", "Без входа", false);

	private final AuthProperties properties;
	private final Accounts accounts;
	private final SessionTokens tokens;
	private final ReactiveAuthenticationManager passwords;
	private final Cache<String, AtomicInteger> failures = Caffeine.newBuilder()
		.expireAfterWrite(LOCKOUT)
		.maximumSize(10_000)
		.build();

	public AuthController(AuthProperties properties, Accounts accounts, SessionTokens tokens,
			ReactiveAuthenticationManager passwords) {
		this.properties = properties;
		this.accounts = accounts;
		this.tokens = tokens;
		this.passwords = passwords;
	}

	@PostMapping("/login")
	@Operation(summary = "Вход по логину и паролю", description = "Ставит cookie сессии на 12 часов")
	public Mono<ResponseEntity<Object>> login(@RequestBody LoginRequest request, ServerWebExchange exchange) {
		if (!properties.enabled()) {
			return Mono.just(ResponseEntity.ok(GUEST));
		}
		String login = request.username() == null ? "" : request.username().trim();
		String key = login.toLowerCase(Locale.ROOT);
		AtomicInteger failed = failures.getIfPresent(key);
		if (failed != null && failed.get() >= MAX_FAILURES) {
			return Mono.just(problem(HttpStatus.TOO_MANY_REQUESTS, "Слишком много неверных паролей",
					"Вход для этого логина закрыт на 10 минут"));
		}
		String password = request.password() == null ? "" : request.password();
		return passwords.authenticate(new UsernamePasswordAuthenticationToken(login, password))
			.map(auth -> {
				failures.invalidate(key);
				String name = accounts.name(auth.getName()).orElse(auth.getName());
				exchange.getResponse().addCookie(tokens.cookie(tokens.issue(auth.getName(), name), secure(exchange)));
				return ResponseEntity.ok((Object) new UserDto(auth.getName(), name, true));
			})
			.onErrorResume(AuthenticationException.class, ex -> {
				failures.get(key, k -> new AtomicInteger()).incrementAndGet();
				return Mono.just(problem(HttpStatus.UNAUTHORIZED, "Вход не выполнен", "Неверный логин или пароль"));
			});
	}

	@PostMapping("/logout")
	@Operation(summary = "Выход", description = "Удаляет cookie сессии")
	public ResponseEntity<Void> logout(ServerWebExchange exchange) {
		exchange.getResponse().addCookie(tokens.clear(secure(exchange)));
		return ResponseEntity.noContent().build();
	}

	@GetMapping("/me")
	@Operation(summary = "Текущий пользователь", description = "401, если сессии нет; без входа в сервисе - гость")
	public Mono<ResponseEntity<Object>> me() {
		if (!properties.enabled()) {
			return Mono.just(ResponseEntity.ok(GUEST));
		}
		return ReactiveSecurityContextHolder.getContext()
			.mapNotNull(SecurityContext::getAuthentication)
			.filter(Authentication::isAuthenticated)
			.map(auth -> ResponseEntity.ok((Object) user(auth)))
			.defaultIfEmpty(problem(HttpStatus.UNAUTHORIZED, "Нужен вход", "Войдите в «Час пик»: сессии нет или она истекла"));
	}

	private UserDto user(Authentication auth) {
		if (auth.getPrincipal() instanceof Jwt jwt) {
			String name = jwt.getClaimAsString("name");
			return new UserDto(jwt.getSubject(), name == null ? jwt.getSubject() : name, true);
		}
		return new UserDto(auth.getName(), accounts.name(auth.getName()).orElse(auth.getName()), true);
	}

	private static ResponseEntity<Object> problem(HttpStatus status, String title, String detail) {
		ProblemDetail problem = ProblemDetail.forStatusAndDetail(status, detail);
		problem.setType(AUTH);
		problem.setTitle(title);
		return ResponseEntity.status(status).contentType(MediaType.APPLICATION_PROBLEM_JSON).body(problem);
	}

	/** За nginx схему запроса видно только по X-Forwarded-Proto. */
	private static boolean secure(ServerWebExchange exchange) {
		String proto = exchange.getRequest().getHeaders().getFirst("X-Forwarded-Proto");
		return "https".equalsIgnoreCase(proto) || "https".equalsIgnoreCase(exchange.getRequest().getURI().getScheme());
	}

}
