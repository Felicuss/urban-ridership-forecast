package ru.mojarung.tramload;

import java.nio.file.Path;

import ru.mojarung.tramload.domain.ForecastModel;
import ru.mojarung.tramload.infrastructure.ArtifactLoader;

/** Настоящий каталог artifacts/ репозитория: тесты проверяют те же файлы, что читает сервис. */
public final class TestArtifacts {

	private static ForecastModel model;

	private TestArtifacts() {
	}

	public static Path dir() {
		String dir = System.getProperty("tramload.artifacts.dir");
		if (dir == null) {
			throw new IllegalStateException("не задан tramload.artifacts.dir, запускайте тесты через gradlew test");
		}
		return Path.of(dir);
	}

	/** Корень репозитория: там лежат forecasts/ с сабмитами. */
	public static Path repoRoot() {
		return dir().getParent();
	}

	public static synchronized ForecastModel model() {
		if (model == null) {
			model = new ArtifactLoader().load(dir());
		}
		return model;
	}

}
