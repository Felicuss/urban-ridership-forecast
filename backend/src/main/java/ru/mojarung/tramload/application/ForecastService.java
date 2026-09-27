package ru.mojarung.tramload.application;

import java.time.YearMonth;
import java.util.ArrayList;
import java.util.List;

import ru.mojarung.tramload.domain.Aggregator;
import ru.mojarung.tramload.domain.Aggregator.Point;
import ru.mojarung.tramload.domain.ForecastModel;
import ru.mojarung.tramload.domain.Granularity;
import ru.mojarung.tramload.domain.Scenario;
import ru.mojarung.tramload.domain.Source;

/** Прогноз по маршруту, остановке, участку или сети на интервале с нужным шагом, в том числе по сценарию. */
public final class ForecastService {

	static final String NOTE_ESTIMATE = "Остановки и участки - оценка: прогноз маршрута разложен по долям остановок, "
			+ "в валидациях остановки посадки нет";
	static final String NOTE_YEAR = "Январь-октябрь 2026 - качественный прогноз по сезонному индексу городского "
			+ "трамвая, коридор ±12 %; ползунки модели на них не влияют, события сценария - на сутках, неделе и месяце";

	static final String NOTE_FACT = "Январь-октябрь 2025 - факт: успешные валидации из данных организаторов, коридора нет";
	static final String NOTE_OUTLOOK = "2026 год - оценка: помесячный прогноз по сезонному индексу разложен по дням с учётом "
			+ "типа дня, дня недели, школьных каникул и погоды Open-Meteo (поправки оценены по факту 2025 года), по часам - "
			+ "формой суток декабря 2025, коридор ±12 %; события сценария её умножают, ползунки модели - нет";

	private final ForecastModel model;
	private final QueryResolver resolver;
	private final ScenarioService scenarios;
	private final Aggregator aggregator;

	public ForecastService(ForecastModel model, QueryResolver resolver, ScenarioService scenarios,
			Aggregator aggregator) {
		this.model = model;
		this.resolver = resolver;
		this.scenarios = scenarios;
		this.aggregator = aggregator;
	}

	public ForecastResult forecast(ForecastQuery query) {
		return forecast(resolver.resolve(query), scenarios.defaultScenario());
	}

	public ScenarioComparison compare(ForecastQuery query, Scenario scenario) {
		ResolvedQuery resolved = resolver.resolve(query);
		return new ScenarioComparison(forecast(resolved, scenario), forecast(resolved, scenarios.defaultScenario()),
				scenario);
	}

	ForecastResult forecast(ResolvedQuery q, Scenario scenario) {
		double[] prediction = scenarios.prediction(scenario);
		List<Point> points = q.isYear() ? year(q, prediction)
				: aggregator.series(prediction, scenario.events(), q.target().weights(), q.from(), q.to(), q.hours(),
						q.granularity());
		List<String> notes = new ArrayList<>();
		if (q.target().isEstimate()) {
			notes.add(NOTE_ESTIMATE);
		}
		if (q.isYear()) {
			notes.add(NOTE_YEAR);
		}
		if (points.stream().anyMatch(p -> p.source() == Source.FACT)) {
			notes.add(NOTE_FACT);
		}
		if (!q.isYear() && points.stream().anyMatch(p -> p.source() == Source.OUTLOOK)) {
			notes.add(NOTE_OUTLOOK);
		}
		return new ForecastResult(q, points, Aggregator.total(points), notes);
	}

	/** Ноябрь и декабрь - из почасового прогноза сценария, дальше - годовой файл с сезонным индексом. */
	private List<Point> year(ResolvedQuery q, double[] prediction) {
		List<Point> hourly = aggregator.series(prediction, q.target().weights(), model.grid().start(),
				model.grid().end(), q.hours(), Granularity.MONTH);
		List<Point> out = new ArrayList<>(hourly);
		for (YearMonth month : model.year().months()) {
			if (month.isAfter(YearMonth.from(model.grid().end()))) {
				out.add(Point.of(month.toString(), model.year().total(month, q.target().weights()), Source.OUTLOOK));
			}
		}
		return out;
	}

}
