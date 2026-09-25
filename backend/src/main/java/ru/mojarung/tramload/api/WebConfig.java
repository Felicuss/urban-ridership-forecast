package ru.mojarung.tramload.api;

import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;

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
			.exposedHeaders("Content-Disposition", "ETag")
			.maxAge(3600);
	}

	@Bean
	OpenAPI openApi() {
		return new OpenAPI().info(new Info().title("Прогноз загрузки трамвайных маршрутов Москвы")
			.version("v1")
			.description("Почасовой прогноз посадок на ноябрь-декабрь 2025, сценарии с ползунками, остановки и "
					+ "участки, тепловая карта, выгрузка CSV и XLSX. Ошибки - Problem Details (RFC 9457)."));
	}

}
