package ru.mojarung.tramload.api.dto;

/** Ползунок: тип number, integer, boolean, date или datetime; источник значения по умолчанию. */
public record CoefficientDto(String key, String label, String group, String type, Object defaultValue, Object min,
		Object max, Double step, String source) {
}
