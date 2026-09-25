package ru.mojarung.tramload.domain;

import java.nio.ByteBuffer;

import ru.mojarung.tramload.domain.coefficient.CoefficientCatalog;
import ru.mojarung.tramload.domain.network.StopNetwork;

/**
 * Всё, что сервис загрузил из artifacts/ при старте. Неизменяемо: запросы только читают модель,
 * поэтому экземпляры сервиса не хранят состояния и масштабируются горизонтально.
 */
public record ForecastModel(
		ForecastComponents components,
		ModelConstants constants,
		CoefficientCatalog catalog,
		StopNetwork network,
		Intervals intervals,
		YearForecast year,
		ModelInfo info,
		ByteBuffer networkGeoJson) {

	public ForecastModel {
		networkGeoJson = networkGeoJson.asReadOnlyBuffer();
	}

	public ForecastGrid grid() {
		return components.grid();
	}

	/** GeoJSON трасс и остановок из network.geojson: только чтение и без копирования на каждый запрос. */
	@Override
	public ByteBuffer networkGeoJson() {
		return networkGeoJson.duplicate();
	}

}
