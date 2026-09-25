package ru.mojarung.tramload.api.dto;

import java.util.List;

/** Значения маршрута или остановки по часам, в порядке hours ответа. */
public record SeriesDto(String id, List<Double> values) {
}
