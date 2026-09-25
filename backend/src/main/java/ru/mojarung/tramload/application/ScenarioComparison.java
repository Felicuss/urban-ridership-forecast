package ru.mojarung.tramload.application;

import ru.mojarung.tramload.domain.Scenario;

/** Ряд сценария рядом с базовым прогнозом: фронт показывает оба и разницу. */
public record ScenarioComparison(ForecastResult scenario, ForecastResult baseline, Scenario applied) {
}
