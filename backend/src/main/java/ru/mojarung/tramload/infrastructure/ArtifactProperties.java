package ru.mojarung.tramload.infrastructure;

import java.nio.file.Path;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Где лежат артефакты модели. В контейнере это /app/artifacts, при локальном запуске - ../artifacts.
 *
 * @param dir каталог с manifest.json
 * @param scenarioCacheSize сколько пересчитанных сценариев держать в памяти (один - около 120 КБ)
 */
@ConfigurationProperties("tramload.artifacts")
public record ArtifactProperties(Path dir, int scenarioCacheSize) {

	public ArtifactProperties {
		if (dir == null) {
			throw new IllegalArgumentException("не задан tramload.artifacts.dir");
		}
		if (scenarioCacheSize <= 0) {
			scenarioCacheSize = 256;
		}
	}

}
