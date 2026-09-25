package ru.mojarung.tramload.domain;

/** Шаг ряда прогноза. */
public enum Granularity {

	HOUR, DAY, MONTH;

	public String code() {
		return name().toLowerCase();
	}

}
