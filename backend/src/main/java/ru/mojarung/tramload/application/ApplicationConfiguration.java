package ru.mojarung.tramload.application;

import java.util.concurrent.Executors;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import ru.mojarung.tramload.domain.Aggregator;
import ru.mojarung.tramload.domain.ForecastEngine;
import ru.mojarung.tramload.domain.ForecastModel;
import ru.mojarung.tramload.domain.agent.AgentMemory;
import ru.mojarung.tramload.domain.agent.AgentTools;
import ru.mojarung.tramload.domain.agent.LanguageModel;
import ru.mojarung.tramload.domain.news.NewsArchive;
import ru.mojarung.tramload.domain.news.NewsSource;

/** Сценарии использования поверх загруженной модели. Все сервисы без состояния, кроме кэша сценариев. */
@Configuration(proxyBeanMethods = false)
public class ApplicationConfiguration {

	@Bean
	QueryResolver queryResolver(ForecastModel model) {
		return new QueryResolver(model);
	}

	@Bean
	ScenarioService scenarioService(ForecastModel model, ForecastEngine engine,
			@Value("${tramload.artifacts.scenario-cache-size:256}") int cacheSize) {
		return new ScenarioService(model, engine, cacheSize);
	}

	@Bean
	ForecastService forecastService(ForecastModel model, QueryResolver resolver, ScenarioService scenarios,
			Aggregator aggregator) {
		return new ForecastService(model, resolver, scenarios, aggregator);
	}

	@Bean
	ExportService exportService(ForecastModel model, QueryResolver resolver, ForecastService forecasts) {
		return new ExportService(model, resolver, forecasts);
	}

	@Bean
	NetworkLoadService networkLoadService(ForecastModel model, ScenarioService scenarios, Aggregator aggregator) {
		return new NetworkLoadService(model, scenarios, aggregator);
	}

	@Bean
	NewsService newsService(NewsArchive archive, NewsSource live, ForecastModel model) {
		return new NewsService(archive, live, model.grid(), model.timeline().end());
	}

	/** Агент ходит в модель и MCP-сервер по сети: каждый ход на своём виртуальном потоке. */
	@Bean
	AgentService agentService(LanguageModel model, AgentTools tools, AgentMemory memory) {
		return new AgentService(model, tools, memory, Executors.newVirtualThreadPerTaskExecutor());
	}

}
