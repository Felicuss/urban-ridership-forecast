package ru.mojarung.tramload.api.dto;

/**
 * Точка сценария рядом с базовым прогнозом. deltaPct пустой, если база нулевая. peak и peakAt - самый
 * загруженный час сценария внутри точки за сутки или месяц, у почасовых точек null.
 */
public record ScenarioPointDto(String period, double p50, double p10, double p90, double baseline, double delta,
		Double deltaPct, String source, Double peak, String peakAt) {
}
