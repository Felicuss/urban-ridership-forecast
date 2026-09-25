package ru.mojarung.tramload.api.dto;

/** Остановка маршрута по ходу рейса и её доля посадок маршрута (оценка). */
public record RouteStopDto(int direction, int seq, String stopId, String name, double lat, double lon, double share) {
}
