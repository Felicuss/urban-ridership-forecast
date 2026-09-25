package ru.mojarung.tramload.domain;

/** Тип дня для профиля: праздник считается воскресеньем, рабочая суббота - будним днём. */
public enum DayKind {

	WORKDAY, SATURDAY, SUNDAY;

	public static DayKind parse(String value) {
		return switch (value) {
			case "workday" -> WORKDAY;
			case "saturday" -> SATURDAY;
			case "sunday" -> SUNDAY;
			default -> throw new IllegalArgumentException("неизвестный тип дня: " + value);
		};
	}

	public String code() {
		return name().toLowerCase();
	}

}
