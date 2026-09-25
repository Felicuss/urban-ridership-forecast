package ru.mojarung.tramload.infrastructure;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import ru.mojarung.tramload.domain.Aggregator;
import ru.mojarung.tramload.domain.ForecastEngine;
import ru.mojarung.tramload.domain.ForecastModel;
import ru.mojarung.tramload.domain.Scenario;

/** Загрузка модели при старте и сборка доменных объектов, которые дальше только читаются. */
@Configuration(proxyBeanMethods = false)
public class ModelConfiguration {

	private static final Logger LOG = LoggerFactory.getLogger(ModelConfiguration.class);
	private static final double SELF_CHECK_TOLERANCE = 1e-6;

	@Bean
	ForecastModel forecastModel(ArtifactProperties properties) {
		long started = System.nanoTime();
		ForecastModel model = new ArtifactLoader().load(properties.dir());
		selfCheck(model);
		LOG.info("artifacts {} загружены за {} мс: {} ячеек, {} остановок, модель {} от {}", properties.dir(),
				(System.nanoTime() - started) / 1_000_000, model.grid().size(), model.network().stops().size(),
				model.info().modelVersion(), model.info().forecastOrigin());
		return model;
	}

	@Bean
	ForecastEngine forecastEngine(ForecastModel model) {
		return new ForecastEngine(model.components(), model.constants());
	}

	@Bean
	Aggregator aggregator(ForecastModel model) {
		return new Aggregator(model.timeline(), model.intervals());
	}

	/**
	 * Формула сервиса со значениями по умолчанию обязана дать тот же прогноз, что экспорт на Python.
	 * Если код и артефакты разошлись по версии, сервис не стартует.
	 */
	static void selfCheck(ForecastModel model) {
		double[] computed = new ForecastEngine(model.components(), model.constants())
			.compute(Scenario.of(model.catalog().defaults()));
		double[] exported = model.components().exportedPrediction();
		for (int cell = 0; cell < computed.length; cell++) {
			if (Math.abs(computed[cell] - exported[cell]) > SELF_CHECK_TOLERANCE) {
				throw new ArtifactValidationException("прогноз по умолчанию разошёлся с экспортом в ячейке " + cell
						+ ": " + computed[cell] + " против " + exported[cell]);
			}
		}
	}

}
