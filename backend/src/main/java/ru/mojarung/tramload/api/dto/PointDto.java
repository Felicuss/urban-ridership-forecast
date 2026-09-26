package ru.mojarung.tramload.api.dto;

/**
 * Точка ряда: медиана и коридор p10-p90, посадок за период; source - fact, forecast или outlook.
 * У точек за сутки и месяц peak - посадки в самый загруженный час, peakAt - этот час; у почасовых точек null.
 */
public record PointDto(String period, double p50, double p10, double p90, String source, Double peak, String peakAt) {
}
