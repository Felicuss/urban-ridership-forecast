package ru.mojarung.tramload.domain.network;

import java.util.List;

/** Остановка: id справочника (g...) или узла OSM (o...), источник координат и маршруты, которые через неё идут. */
public record Stop(String id, String name, double lat, double lon, String source, List<Integer> routes) {

	public Stop {
		routes = List.copyOf(routes);
	}

}
