package ru.mojarung.tramload.api.dto;

import java.util.List;

/** Остановка: source = reference (справочник), osm или osm+reference (узел OSM совпал со справочником). */
public record StopDto(String id, String name, double lat, double lon, String source, List<Integer> routes) {
}
