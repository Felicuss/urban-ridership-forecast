package ru.mojarung.tramload.api;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;

/** CORS для фронта и описание OpenAPI, по которому фронт генерирует клиента. */
@Configuration(proxyBeanMethods = false)
public class WebConfig implements WebFluxConfigurer {

	private final List<String> allowedOrigins;

	public WebConfig(@Value("${tramload.cors.allowed-origins:}") List<String> allowedOrigins) {
		this.allowedOrigins = List.copyOf(allowedOrigins);
	}

	@Override
	public void addCorsMappings(CorsRegistry registry) {
		registry.addMapping("/api/**")
			.allowedOrigins(allowedOrigins.toArray(String[]::new))
			.allowedMethods("GET", "POST")
			.exposedHeaders("Content-Disposition", "ETag", "X-Rows")
			.maxAge(3600);
	}

	/** Потоки для записи выгрузок: виртуальные, блокирующая запись в OutputStream их не занимает надолго. */
	@Bean(destroyMethod = "close")
	ExecutorService exportExecutor() {
		return Executors.newVirtualThreadPerTaskExecutor();
	}

	@Bean
	OpenAPI openApi() {
		return new OpenAPI().info(new Info().title("Час пик: прогноз загрузки трамвайных маршрутов Москвы")
			.version("v1")
			.description("Почасовой прогноз посадок на ноябрь-декабрь 2025, сценарии с ползунками, остановки и "
					+ "участки, тепловая карта, выгрузка CSV и XLSX. Ошибки - Problem Details (RFC 9457)."))
			// без схемы в Swagger UI нет кнопки Authorize, и «Try it out» без входа в интерфейс получает 401
			.components(new Components().addSecuritySchemes("basic", new SecurityScheme()
				.type(SecurityScheme.Type.HTTP).scheme("basic")
				.description("Логин и пароль диспетчера из AUTH_USERS, значения по умолчанию - в README")))
			.addSecurityItem(new SecurityRequirement().addList("basic"));
	}

}
