package ru.mojarung.tramload.application;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import ru.mojarung.tramload.domain.Aggregator;
import ru.mojarung.tramload.domain.ForecastGrid;
import ru.mojarung.tramload.domain.ForecastModel;
import ru.mojarung.tramload.domain.HourWindow;
import ru.mojarung.tramload.domain.Scenario;
import ru.mojarung.tramload.domain.Source;
import ru.mojarung.tramload.domain.Timeline;
import ru.mojarung.tramload.domain.ValidationException;

/**
 * Нагрузка всей сети на дату по часам: кадры для тепловой карты. Маршруты и остановки считаются
 * за один проход по заранее собранным долям, ответ занимает около 12 тыс. чисел.
 */
public final class NetworkLoadService {

	private final ForecastModel model;
	private final ScenarioService scenarios;
	private final Aggregator aggregator;
	private final Map<String, Map<Integer, Double>> stopWeights;

	public NetworkLoadService(ForecastModel model, ScenarioService scenarios, Aggregator aggregator) {
		this.model = model;
		this.scenarios = scenarios;
		this.aggregator = aggregator;
		this.stopWeights = model.network().allStopWeights();
	}

	public NetworkLoad load(LocalDate date, HourWindow hours, Scenario scenario) {
		Timeline timeline = model.timeline();
		if (date == null || !timeline.contains(date)) {
			throw ValidationException.of("date", "укажите дату в шкале " + timeline.start() + " - " + timeline.end());
		}
		HourWindow window = hours == null ? HourWindow.ALL_DAY : hours;
		double[] prediction = scenarios.prediction(scenario);
		int day = timeline.dayIndex(date);
		ForecastGrid grid = model.grid();
		List<Series> routes = new ArrayList<>();
		for (int route : grid.routes()) {
			routes.add(new Series(String.valueOf(route), values(prediction, scenario, Map.of(route, 1.0), day, window)));
		}
		List<Series> stops = new ArrayList<>();
		stopWeights.forEach((stop, weights) -> stops.add(new Series(stop, values(prediction, scenario, weights, day, window))));
		List<Integer> hourList = new ArrayList<>();
		for (int h = window.first(); h <= window.last(); h++) {
			hourList.add(h);
		}
		return new NetworkLoad(date, timeline.day(day).source(), hourList, routes, stops);
	}

	private List<Double> values(double[] prediction, Scenario scenario, Map<Integer, Double> weights, int day,
			HourWindow window) {
		List<Double> out = new ArrayList<>(window.last() - window.first() + 1);
		for (int h = window.first(); h <= window.last(); h++) {
			out.add(aggregator.cellSum(prediction, scenario.events(), weights, day, h));
		}
		return out;
	}

	/** Кадры по часам: у каждого маршрута и остановки значения в порядке hours. */
	public record NetworkLoad(LocalDate date, Source source, List<Integer> hours, List<Series> routes,
			List<Series> stops) {

		public NetworkLoad {
			hours = List.copyOf(hours);
			routes = List.copyOf(routes);
			stops = List.copyOf(stops);
		}

	}

	public record Series(String id, List<Double> values) {

		public Series {
			values = List.copyOf(values);
		}

	}

}
