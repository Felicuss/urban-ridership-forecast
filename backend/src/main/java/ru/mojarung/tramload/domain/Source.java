package ru.mojarung.tramload.domain;

/** Откуда значение: факт валидаций, почасовой прогноз модели или оценка по сезонному индексу. */
public enum Source {

	FACT, FORECAST, OUTLOOK;

	public String code() {
		return name().toLowerCase();
	}

	public static Source parse(String value) {
		return valueOf(value.toUpperCase());
	}

}
