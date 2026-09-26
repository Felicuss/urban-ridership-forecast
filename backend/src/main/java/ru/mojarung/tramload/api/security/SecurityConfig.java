package ru.mojarung.tramload.api.security;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.savedrequest.NoOpServerRequestCache;

/**
 * Базовая авторизация диспетчера. Интерфейс входит по логину и паролю и получает сессию в HttpOnly-cookie,
 * MCP-сервер и скрипты могут прийти с логином и паролем (Basic) или с токеном в Authorization: Bearer.
 * Открыты только вход, проверка здоровья и документация API. Состояние на сервере не хранится.
 */
@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableConfigurationProperties(AuthProperties.class)
public class SecurityConfig {

	private static final String[] PUBLIC = { "/api/v1/auth/login", "/api/v1/auth/logout", "/api/v1/auth/me",
			"/actuator/health", "/actuator/health/**", "/api/v1/openapi", "/api/v1/openapi/**", "/swagger-ui.html",
			"/swagger-ui/**", "/webjars/**" };

	@Bean
	PasswordEncoder passwordEncoder() {
		return PasswordEncoderFactories.createDelegatingPasswordEncoder();
	}

	@Bean
	Accounts accounts(AuthProperties properties, PasswordEncoder encoder) {
		return Accounts.parse(properties.users(), encoder);
	}

	@Bean
	ReactiveUserDetailsService userDetailsService(Accounts accounts) {
		return accounts.userDetails();
	}

	@Bean
	ReactiveAuthenticationManager passwordAuthentication(ReactiveUserDetailsService users, PasswordEncoder encoder) {
		UserDetailsRepositoryReactiveAuthenticationManager manager = new UserDetailsRepositoryReactiveAuthenticationManager(users);
		manager.setPasswordEncoder(encoder);
		return manager;
	}

	@Bean
	SessionTokens sessionTokens(AuthProperties properties) {
		return new SessionTokens(SessionTokens.key(properties.secret(), properties.users()), properties.sessionTtl());
	}

	@Bean
	SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http, AuthProperties properties, SessionTokens tokens,
			ReactiveAuthenticationManager passwordAuthentication) {
		http.csrf(ServerHttpSecurity.CsrfSpec::disable)
			.formLogin(ServerHttpSecurity.FormLoginSpec::disable)
			.logout(ServerHttpSecurity.LogoutSpec::disable)
			.requestCache(cache -> cache.requestCache(NoOpServerRequestCache.getInstance()))
			.securityContextRepository(NoOpServerSecurityContextRepository.getInstance());
		if (!properties.enabled()) {
			return http.httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
				.authorizeExchange(exchanges -> exchanges.anyExchange().permitAll())
				.build();
		}
		ProblemEntryPoint entryPoint = new ProblemEntryPoint();
		return http
			.authorizeExchange(exchanges -> exchanges
				.pathMatchers(HttpMethod.OPTIONS).permitAll()
				.pathMatchers(PUBLIC).permitAll()
				.pathMatchers("/api/**", "/actuator/**").authenticated()
				.anyExchange().permitAll())
			.httpBasic(basic -> basic.authenticationManager(passwordAuthentication).authenticationEntryPoint(entryPoint))
			.oauth2ResourceServer(server -> server
				.bearerTokenConverter(new SessionCookieConverter())
				.authenticationEntryPoint(entryPoint)
				.jwt(jwt -> jwt.jwtDecoder(tokens.decoder())))
			.exceptionHandling(errors -> errors.authenticationEntryPoint(entryPoint))
			.build();
	}

}
