package ru.mojarung.tramload.application;

/** Горизонт из задания: день по часам, месяц по дням, год по месяцам (качественный прогноз). */
public enum Horizon {

	DAY, MONTH, YEAR;

	public String code() {
		return name().toLowerCase();
	}

}
