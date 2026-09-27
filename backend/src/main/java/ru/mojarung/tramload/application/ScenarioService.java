package ru.mojarung.tramload.application;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.OptionalInt;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

import ru.mojarung.tramload.domain.ForecastEngine;
import ru.mojarung.tramload.domain.ForecastGrid;
import ru.mojarung.tramload.domain.ForecastModel;
import ru.mojarung.tramload.domain.HourWindow;
import ru.mojarung.tramload.domain.Scenario;
import ru.mojarung.tramload.domain.ScenarioEvent;
import ru.mojarung.tramload.domain.ValidationException;
import ru.mojarung.tramload.domain.ValidationException.Violation;

/**
 * Сценарии: переопределения ползунков и события превращаются в {@link Scenario}, пересчёт всей сетки
 * занимает доли миллисекунды и кэшируется по значению сценария, так что повтор ползунка не считается заново.
 */
public final class ScenarioService {

	public static final int MAX_EVENTS = 20;
	public static final double MAX_EVENT_MULTIPLIER = 5.0;
	private static final int MAX_LABEL = 200;

	private final ForecastModel model;
	private final ForecastEngine engine;
	private final Scenario defaultScenario;
	private final double[] defaultPrediction;
	private final Cache<Scenario, double[]> cache;

	public ScenarioService(ForecastModel model, ForecastEngine engine, int cacheSize) {
		this.model = model;
		this.engine = engine;
		this.defaultScenario = Scenario.of(model.catalog().defaults());
		this.defaultPrediction = engine.compute(defaultScenario);
		this.cache = Caffeine.newBuilder().maximumSize(cacheSize).build();
	}

	public Scenario defaultScenario() {
		return defaultScenario;
	}

	public Scenario resolve(Map<String, ?> coefficients, List<EventInput> events) {
		List<EventInput> input = events == null ? List.of() : events;
		if (input.size() > MAX_EVENTS) {
			throw ValidationException.of("events", "не больше " + MAX_EVENTS + " событий в сценарии");
		}
		List<Violation> violations = new ArrayList<>();
		List<ScenarioEvent> parsed = new ArrayList<>();
		for (int i = 0; i < input.size(); i++) {
			ScenarioEvent event = event(input.get(i), "events[" + i + "]", violations);
			if (event != null) {
				parsed.add(event);
			}
		}
		if (!violations.isEmpty()) {
			throw new ValidationException(violations);
		}
		return new Scenario(model.catalog().resolve(coefficients), parsed);
	}

	/** Почасовой прогноз сценария. Массив общий для всех запросов этого сценария: только для чтения. */
	public double[] prediction(Scenario scenario) {
		if (scenario.equals(defaultScenario)) {
			return defaultPrediction;
		}
		return cache.get(scenario, engine::compute);
	}

	/** Шаги формулы за сутки по маршруту или сети (route = null) для водопада «из чего сложился прогноз». */
	public ForecastEngine.Explanation explain(Scenario scenario, Integer route, java.time.LocalDate date) {
		ForecastGrid grid = model.grid();
		if (route != null && !grid.hasRoute(route)) {
			throw ValidationException.of("route", "маршрута " + route + " нет в прогнозе");
		}
		if (!grid.contains(date)) {
			throw ValidationException.of("date", "разбор есть для дат почасового прогноза " + grid.start() + " - " + grid.end());
		}
		return engine.explain(scenario, route, date);
	}

	public double[] defaultPrediction() {
		return defaultPrediction;
	}

	private ScenarioEvent event(EventInput e, String field, List<Violation> violations) {
		int before = violations.size();
		ForecastGrid grid = model.grid();
		if (e.route() != null && !grid.hasRoute(e.route())) {
			violations.add(new Violation(field + ".route", "маршрута " + e.route() + " нет в прогнозе"));
		}
		if (e.from() == null || e.to() == null) {
			violations.add(new Violation(field, "укажите from и to"));
		}
		else if (e.from().isAfter(e.to()) || !grid.contains(e.from()) || !grid.contains(e.to())) {
			violations.add(new Violation(field, "интервал должен идти вперёд и лежать в " + grid.start() + " - " + grid.end()));
		}
		Double m = e.multiplier();
		if (m == null || !Double.isFinite(m) || m < 0 || m > MAX_EVENT_MULTIPLIER) {
			violations.add(new Violation(field + ".multiplier", "множитель от 0 до " + MAX_EVENT_MULTIPLIER));
		}
		if (e.label() != null && e.label().length() > MAX_LABEL) {
			violations.add(new Violation(field + ".label", "подпись длиннее " + MAX_LABEL + " символов"));
		}
		if (violations.size() > before) {
			return null;
		}
		OptionalInt route = e.route() == null ? OptionalInt.empty() : OptionalInt.of(e.route());
		HourWindow hours = e.hours() == null ? HourWindow.ALL_DAY : e.hours();
		return new ScenarioEvent(route, e.from(), e.to(), hours, m, e.label() == null ? "" : e.label());
	}

}
