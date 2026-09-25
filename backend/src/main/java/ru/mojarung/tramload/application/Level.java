package ru.mojarung.tramload.application;

/** Объект прогноза: маршрут, остановка, участок маршрута между двумя остановками или вся сеть. */
public enum Level {

	ROUTE, STOP, SEGMENT, NETWORK;

	public String code() {
		return name().toLowerCase();
	}

}
