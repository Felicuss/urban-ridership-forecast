package ru.mojarung.tramload.domain.coefficient;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeParseException;

/** Тип ползунка и разбор значения из JSON (число, логическое значение или строка ISO-8601). */
public enum CoefficientType {

	NUMBER, INTEGER, BOOLEAN, DATE, DATETIME;

	public static CoefficientType parse(String value) {
		return valueOf(value.toUpperCase());
	}

	/** Приводит значение к типу ползунка или бросает IllegalArgumentException с понятным текстом. */
	public Object coerce(Object raw) {
		return switch (this) {
			case NUMBER -> finite(number(raw));
			case INTEGER -> integer(raw);
			case BOOLEAN -> {
				if (raw instanceof Boolean b) {
					yield b;
				}
				throw new IllegalArgumentException("ожидается true или false");
			}
			case DATE -> parseText(raw, LocalDate::parse, "дата в формате 2025-11-15");
			case DATETIME -> parseText(raw, LocalDateTime::parse, "дата и время в формате 2025-12-16T18:00");
		};
	}

	private static double number(Object raw) {
		if (raw instanceof Number n) {
			return n.doubleValue();
		}
		throw new IllegalArgumentException("ожидается число");
	}

	private static double finite(double value) {
		if (!Double.isFinite(value)) {
			throw new IllegalArgumentException("ожидается конечное число");
		}
		return value;
	}

	private static int integer(Object raw) {
		double value = number(raw);
		if (value != Math.rint(value) || Math.abs(value) > Integer.MAX_VALUE) {
			throw new IllegalArgumentException("ожидается целое число");
		}
		return (int) value;
	}

	private static <T> T parseText(Object raw, java.util.function.Function<String, T> parser, String expected) {
		if (raw instanceof String s) {
			try {
				return parser.apply(s);
			}
			catch (DateTimeParseException ex) {
				throw new IllegalArgumentException("ожидается " + expected, ex);
			}
		}
		throw new IllegalArgumentException("ожидается " + expected);
	}

}
