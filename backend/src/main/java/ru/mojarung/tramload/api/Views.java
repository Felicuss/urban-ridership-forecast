package ru.mojarung.tramload.api;

import java.util.ArrayList;
import java.util.List;

import ru.mojarung.tramload.api.dto.EventDto;
import ru.mojarung.tramload.api.dto.ForecastResponse;
import ru.mojarung.tramload.api.dto.PointDto;
import ru.mojarung.tramload.api.dto.ScenarioPointDto;
import ru.mojarung.tramload.api.dto.ScenarioResponse;
import ru.mojarung.tramload.api.dto.TargetDto;
import ru.mojarung.tramload.application.ForecastResult;
import ru.mojarung.tramload.application.ResolvedQuery;
import ru.mojarung.tramload.application.ScenarioComparison;
import ru.mojarung.tramload.domain.Aggregator.Point;
import ru.mojarung.tramload.domain.ScenarioEvent;
import ru.mojarung.tramload.domain.coefficient.CoefficientCatalog;

/** Ответы API из результатов прикладного слоя. Посадки округляются до десятых. */
final class Views {

	static final String TIMEZONE = "Europe/Moscow";
	static final String UNIT = "посадки (успешные валидации)";

	private Views() {
	}

	static ForecastResponse forecast(ForecastResult r) {
		ResolvedQuery q = r.query();
		return new ForecastResponse(target(q), q.horizon() == null ? null : q.horizon().code(), q.granularity().code(),
				q.from(), q.to(), q.hours().toString(), TIMEZONE, UNIT, r.points().stream().map(Views::point).toList(),
				point(r.total()), r.notes());
	}

	static ScenarioResponse scenario(ScenarioComparison c) {
		ResolvedQuery q = c.scenario().query();
		List<ScenarioPointDto> points = new ArrayList<>();
		for (int i = 0; i < c.scenario().points().size(); i++) {
			points.add(delta(c.scenario().points().get(i), c.baseline().points().get(i)));
		}
		List<EventDto> events = c.applied().events().stream().map(Views::event).toList();
		return new ScenarioResponse(target(q), q.horizon() == null ? null : q.horizon().code(), q.granularity().code(),
				q.from(), q.to(), q.hours().toString(), TIMEZONE, points,
				delta(c.scenario().total(), c.baseline().total()), CoefficientCatalog.values(c.applied().coefficients()),
				events, c.scenario().notes());
	}

	static double round(double value) {
		return Math.round(value * 10.0) / 10.0;
	}

	private static TargetDto target(ResolvedQuery q) {
		return new TargetDto(q.target().level().code(), q.target().id(), q.target().name(), q.target().isEstimate());
	}

	private static PointDto point(Point p) {
		Double peak = p.peak() == null ? null : round(p.peak().value());
		String peakAt = p.peak() == null ? null : p.peak().at();
		return new PointDto(p.period(), round(p.p50()), round(p.p10()), round(p.p90()), p.source().code(), peak, peakAt);
	}

	private static ScenarioPointDto delta(Point scenario, Point baseline) {
		double delta = scenario.p50() - baseline.p50();
		Double pct = baseline.p50() > 0 ? round(100.0 * delta / baseline.p50()) : null;
		Double peak = scenario.peak() == null ? null : round(scenario.peak().value());
		String peakAt = scenario.peak() == null ? null : scenario.peak().at();
		return new ScenarioPointDto(scenario.period(), round(scenario.p50()), round(scenario.p10()),
				round(scenario.p90()), round(baseline.p50()), round(delta), pct, scenario.source().code(), peak, peakAt);
	}

	static EventDto event(ScenarioEvent e) {
		return new EventDto(e.route().isPresent() ? e.route().getAsInt() : null, e.from().toString(), e.to().toString(),
				e.hours().toString(), e.multiplier(), e.label());
	}

}
