package ru.mojarung.tramload.application;

/** Горизонт: день по часам, неделя и месяц по дням (пики нагрузки по суткам), год по месяцам (качественный прогноз). */
public enum Horizon {

	DAY, WEEK, MONTH, YEAR;

	public String code() {
		return name().toLowerCase();
	}

}
