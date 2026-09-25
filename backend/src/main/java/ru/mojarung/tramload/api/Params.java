package ru.mojarung.tramload.api;

import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Arrays;
import java.util.Locale;

import ru.mojarung.tramload.domain.HourWindow;
import ru.mojarung.tramload.domain.ValidationException;

/** Разбор строковых параметров запроса с ошибками в формате поля и понятного текста. */
final class Params {

	private Params() {
	}

	static <E extends Enum<E>> E enumValue(String value, Class<E> type, String field) {
		if (value == null || value.isBlank()) {
			return null;
		}
		try {
			return Enum.valueOf(type, value.trim().toUpperCase(Locale.ROOT));
		}
		catch (IllegalArgumentException ex) {
			String allowed = Arrays.stream(type.getEnumConstants())
				.map(e -> e.name().toLowerCase(Locale.ROOT))
				.reduce((a, b) -> a + ", " + b)
				.orElse("");
			throw ValidationException.of(field, "значение " + value + " не из списка: " + allowed);
		}
	}

	static LocalDate date(String value, String field) {
		if (value == null || value.isBlank()) {
			return null;
		}
		try {
			return LocalDate.parse(value.trim());
		}
		catch (DateTimeParseException ex) {
			throw ValidationException.of(field, "ожидается дата в формате 2025-11-03, получено " + value);
		}
	}

	/** Окно часов «7-9» или один час «8». */
	static HourWindow hours(String value, String field) {
		if (value == null || value.isBlank()) {
			return null;
		}
		String[] parts = value.trim().split("-", -1);
		try {
			int first = Integer.parseInt(parts[0].trim());
			int last = parts.length == 2 ? Integer.parseInt(parts[1].trim()) : first;
			if (parts.length > 2) {
				throw new NumberFormatException(value);
			}
			return new HourWindow(first, last);
		}
		catch (NumberFormatException ex) {
			throw ValidationException.of(field, "ожидается час 0-23 или окно вида 7-9, получено " + value);
		}
		catch (IllegalArgumentException ex) {
			throw ValidationException.of(field, ex.getMessage());
		}
	}

}
