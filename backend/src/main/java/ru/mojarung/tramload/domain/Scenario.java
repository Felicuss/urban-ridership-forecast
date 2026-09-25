package ru.mojarung.tramload.domain;

import java.util.List;

/** Коэффициенты и события одного расчёта. Record с равенством по значению служит ключом кэша. */
public record Scenario(Coefficients coefficients, List<ScenarioEvent> events) {

	public Scenario {
		events = List.copyOf(events);
	}

	public static Scenario of(Coefficients coefficients) {
		return new Scenario(coefficients, List.of());
	}

}
