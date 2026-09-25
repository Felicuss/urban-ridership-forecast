package ru.mojarung.tramload.api.dto;

/** Маршрут в прогнозе: число остановок и посадки за горизонт по умолчанию. */
public record RouteDto(int route, int stops, double forecastTotal, double forecastPerDay) {
}
