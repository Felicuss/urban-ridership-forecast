package ru.mojarung.tramload.domain.coefficient;

/**
 * Описание ползунка из coefficients.json. Для чисел min и max - числа, для дат - строки ISO-8601.
 * Значение по умолчанию уже приведено к типу ползунка: Double, Integer, Boolean, LocalDate или LocalDateTime.
 */
public record CoefficientSpec(
		String key,
		String label,
		String group,
		CoefficientType type,
		Object defaultValue,
		Object min,
		Object max,
		Double step,
		String source) {
}
