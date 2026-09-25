package ru.mojarung.tramload.application;

import java.util.Map;

/** Объект, по которому считается ряд: маршруты с весами (1 для маршрута и сети, доли для остановки и участка). */
public record Target(Level level, String id, String name, Map<Integer, Double> weights) {

	public Target {
		weights = Map.copyOf(weights);
	}

	/** Прогноз остановок и участков - раскладка маршрута по долям, а не измерение. */
	public boolean isEstimate() {
		return level == Level.STOP || level == Level.SEGMENT;
	}

}
