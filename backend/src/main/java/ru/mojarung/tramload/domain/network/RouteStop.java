package ru.mojarung.tramload.domain.network;

/** Остановка на маршруте в направлении: порядковый номер по ходу рейса и доля посадок маршрута. */
public record RouteStop(int route, int direction, int seq, String stopId, double share) {
}
