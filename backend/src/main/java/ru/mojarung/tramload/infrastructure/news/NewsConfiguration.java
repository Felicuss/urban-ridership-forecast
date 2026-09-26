package ru.mojarung.tramload.infrastructure.news;

import java.net.URI;
import java.net.http.HttpClient;
import java.time.Clock;
import java.time.Duration;
import java.util.HashSet;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import ru.mojarung.tramload.domain.ForecastModel;
import ru.mojarung.tramload.domain.news.NewsArchive;
import ru.mojarung.tramload.domain.news.NewsSource;
import ru.mojarung.tramload.infrastructure.ArtifactProperties;
import ru.mojarung.tramload.infrastructure.NewsArchiveLoader;

/** Сбои из новостей: архив из артефактов и живая лента канала, если задан её адрес. */
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(NewsConfiguration.NewsProperties.class)
public class NewsConfiguration {

	/**
	 * @param liveUrl веб-версия канала; пусто - только архив
	 * @param refresh как часто перечитывать ленту
	 * @param timeout сколько ждать ответа канала
	 */
	@ConfigurationProperties("tramload.news")
	public record NewsProperties(String liveUrl, Duration refresh, Duration timeout) {

		public NewsProperties {
			refresh = refresh == null ? Duration.ofMinutes(10) : refresh;
			timeout = timeout == null ? Duration.ofSeconds(6) : timeout;
		}

	}

	@Bean
	NewsArchive newsArchive(ArtifactProperties artifacts) {
		return NewsArchiveLoader.load(artifacts.dir());
	}

	@Bean
	NewsSource newsSource(NewsProperties properties, ForecastModel model) {
		if (properties.liveUrl() == null || properties.liveUrl().isBlank()) {
			return NewsSource.LiveNews::off;
		}
		HttpClient http = HttpClient.newBuilder()
			.connectTimeout(properties.timeout())
			.followRedirects(HttpClient.Redirect.NORMAL)
			.build();
		return new TelegramNewsSource(http, URI.create(properties.liveUrl()), properties.refresh(), properties.timeout(),
				new HashSet<>(model.grid().routes()), Clock.systemUTC());
	}

}
