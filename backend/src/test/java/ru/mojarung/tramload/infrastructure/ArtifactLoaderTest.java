package ru.mojarung.tramload.infrastructure;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import ru.mojarung.tramload.TestArtifacts;

/** Испорченный или устаревший каталог артефактов должен останавливать запуск с понятной причиной. */
class ArtifactLoaderTest {

	@TempDir
	Path dir;

	@Test
	void changedFileFailsSha256Check() throws IOException {
		copyArtifacts();
		Path components = dir.resolve("forecast_components.csv");
		String text = Files.readString(components, StandardCharsets.UTF_8);
		Files.writeString(components, text.replaceFirst("\n1,2025-11-01,8,", "\n1,2025-11-01,9,"), StandardCharsets.UTF_8);

		assertThatThrownBy(() -> new ArtifactLoader().load(dir)).isInstanceOf(ArtifactValidationException.class)
			.hasMessageContaining("forecast_components.csv")
			.hasMessageContaining("sha256");
	}

	@Test
	void rowCountMismatchIsReported() throws IOException {
		copyArtifacts();
		Path manifest = dir.resolve("manifest.json");
		Files.writeString(manifest, Files.readString(manifest).replace("\"rows\": 14640", "\"rows\": 14639"));

		assertThatThrownBy(() -> new ArtifactLoader().load(dir)).isInstanceOf(ArtifactValidationException.class)
			.hasMessageContaining("строк данных 14640, в manifest.json 14639");
	}

	@Test
	void missingFileIsReported() throws IOException {
		copyArtifacts();
		Files.delete(dir.resolve("route_stops.csv"));

		assertThatThrownBy(() -> new ArtifactLoader().load(dir)).isInstanceOf(ArtifactValidationException.class)
			.hasMessageContaining("route_stops.csv: файла нет");
	}

	@Test
	void formulaDriftFromExportStopsStartup() throws IOException {
		copyArtifacts();
		Path components = dir.resolve("forecast_components.csv");
		String text = Files.readString(components, StandardCharsets.UTF_8);
		// прогноз по умолчанию в файле больше не соответствует базе: так выглядит рассинхрон кода и артефактов
		Files.writeString(components, text.replaceFirst(",2.1307375\n", ",3.0\n"), StandardCharsets.UTF_8);
		updateSha("forecast_components.csv");

		assertThatThrownBy(() -> ModelConfiguration.selfCheck(new ArtifactLoader().load(dir)))
			.isInstanceOf(ArtifactValidationException.class)
			.hasMessageContaining("разошёлся с экспортом");
	}

	private void copyArtifacts() throws IOException {
		try (Stream<Path> files = Files.list(TestArtifacts.dir())) {
			for (Path f : files.filter(Files::isRegularFile).toList()) {
				Files.copy(f, dir.resolve(f.getFileName()));
			}
		}
	}

	private void updateSha(String name) throws IOException {
		Path manifest = dir.resolve("manifest.json");
		String old = ManifestVerifier.sha256(TestArtifacts.dir().resolve(name));
		Files.writeString(manifest, Files.readString(manifest).replace(old, ManifestVerifier.sha256(dir.resolve(name))));
	}

}
