package ru.mojarung.tramload.infrastructure;

import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import tools.jackson.databind.MappingIterator;
import tools.jackson.dataformat.csv.CsvMapper;
import tools.jackson.dataformat.csv.CsvSchema;

/** Чтение CSV с заголовком в список строк «столбец -> значение». Файлы артефактов небольшие, до 15 тыс. строк. */
final class CsvRows {

	private static final CsvMapper MAPPER = CsvMapper.builder().build();
	private static final CsvSchema HEADER = CsvSchema.emptySchema().withHeader();

	private CsvRows() {
	}

	static List<Map<String, String>> read(Path path) {
		try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);
				MappingIterator<Map<String, String>> rows = MAPPER.readerForMapOf(String.class)
					.with(HEADER)
					.readValues(reader)) {
			return rows.readAll();
		}
		catch (IOException | RuntimeException ex) {
			throw new ArtifactValidationException("не удалось прочитать " + path.getFileName() + ": " + ex.getMessage(),
					ex);
		}
	}

	static String required(Map<String, String> row, String column) {
		String value = row.get(column);
		if (value == null) {
			throw new ArtifactValidationException("нет столбца " + column);
		}
		return value;
	}

	static int integer(Map<String, String> row, String column) {
		return Integer.parseInt(required(row, column));
	}

	static double number(Map<String, String> row, String column) {
		return Double.parseDouble(required(row, column));
	}

	static boolean flag(Map<String, String> row, String column) {
		return integer(row, column) == 1;
	}

}
