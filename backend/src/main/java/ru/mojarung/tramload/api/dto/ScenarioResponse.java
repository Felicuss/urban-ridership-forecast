package ru.mojarung.tramload.api.dto;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

/** Ряд сценария, база и разница; coefficients - итоговые значения всех ползунков сценария. */
public record ScenarioResponse(TargetDto target, String horizon, String granularity, LocalDate from, LocalDate to,
		String hours, String timezone, List<ScenarioPointDto> points, ScenarioPointDto total,
		Map<String, Object> coefficients, List<EventDto> events, List<String> notes) {
}
