package ru.mojarung.tramload.api.dto;

/** Точка ряда: медиана и коридор p10-p90, посадок за период; source - fact, forecast или outlook. */
public record PointDto(String period, double p50, double p10, double p90, String source) {
}
