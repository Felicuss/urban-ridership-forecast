package ru.mojarung.tramload.infrastructure;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.DigestInputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Map;

import tools.jackson.databind.JsonNode;

/**
 * Сверяет каждый файл из manifest.json с диском: sha256 и число строк данных у CSV.
 * Устаревший или испорченный каталог артефактов останавливает запуск, а не отдаёт неверный прогноз.
 */
final class ManifestVerifier {

	static final int SCHEMA_VERSION = 1;

	private ManifestVerifier() {
	}

	static void verify(Path dir, JsonNode manifest) {
		int schema = manifest.path("schema_version").asInt(-1);
		if (schema != SCHEMA_VERSION) {
			throw new ArtifactValidationException(
					"manifest.json: schema_version " + schema + ", сервис понимает " + SCHEMA_VERSION);
		}
		JsonNode files = manifest.path("files");
		if (!files.isObject() || files.isEmpty()) {
			throw new ArtifactValidationException("manifest.json: нет списка files");
		}
		for (Map.Entry<String, JsonNode> entry : files.properties()) {
			verifyFile(dir.resolve(entry.getKey()), entry.getKey(), entry.getValue());
		}
	}

	private static void verifyFile(Path path, String name, JsonNode meta) {
		if (!Files.isRegularFile(path)) {
			throw new ArtifactValidationException(name + ": файла нет в " + path.getParent());
		}
		String expected = meta.path("sha256").asString();
		String actual = sha256(path);
		if (!actual.equals(expected)) {
			throw new ArtifactValidationException(name + ": sha256 " + actual + " не совпадает с manifest.json ("
					+ expected + "). Пересоберите artifacts/ скриптом analysis/s40_export_artifacts.py");
		}
		JsonNode rows = meta.path("rows");
		if (rows.isNumber() && dataRows(path) != rows.asLong()) {
			throw new ArtifactValidationException(
					name + ": строк данных " + dataRows(path) + ", в manifest.json " + rows.asLong());
		}
	}

	static String sha256(Path path) {
		try {
			MessageDigest digest = MessageDigest.getInstance("SHA-256");
			try (InputStream in = new DigestInputStream(Files.newInputStream(path), digest)) {
				in.transferTo(OutputStream.nullOutputStream());
			}
			return HexFormat.of().formatHex(digest.digest());
		}
		catch (IOException | NoSuchAlgorithmException ex) {
			throw new ArtifactValidationException("не удалось посчитать sha256 " + path.getFileName(), ex);
		}
	}

	private static long dataRows(Path path) {
		try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
			return reader.lines().count() - 1;
		}
		catch (IOException ex) {
			throw new ArtifactValidationException("не удалось прочитать " + path.getFileName(), ex);
		}
	}

}
