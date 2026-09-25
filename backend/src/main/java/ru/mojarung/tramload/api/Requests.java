package ru.mojarung.tramload.api;

import java.util.List;

import ru.mojarung.tramload.api.dto.EventDto;
import ru.mojarung.tramload.api.dto.ForecastQueryDto;
import ru.mojarung.tramload.application.EventInput;
import ru.mojarung.tramload.application.ForecastQuery;
import ru.mojarung.tramload.application.Horizon;
import ru.mojarung.tramload.application.Level;
import ru.mojarung.tramload.domain.Granularity;
import ru.mojarung.tramload.domain.ValidationException;

/** Перевод параметров и тел запросов в входы прикладного слоя. Формат проверяется здесь, смысл - там. */
final class Requests {

	private Requests() {
	}

	static ForecastQuery query(ForecastQueryDto q) {
		if (q == null) {
			throw ValidationException.of("query", "укажите, что прогнозировать: level, id, from, to");
		}
		return new ForecastQuery(Params.enumValue(q.level(), Level.class, "level"), q.id(), q.direction(), q.fromStop(),
				q.toStop(), Params.date(q.from(), "from"), Params.date(q.to(), "to"), Params.hours(q.hours(), "hours"),
				Params.enumValue(q.granularity(), Granularity.class, "granularity"),
				Params.enumValue(q.horizon(), Horizon.class, "horizon"));
	}

	static List<EventInput> events(List<EventDto> events) {
		if (events == null) {
			return List.of();
		}
		return events.stream()
			.map(e -> new EventInput(e.route(), Params.date(e.from(), "events.from"), Params.date(e.to(), "events.to"),
					Params.hours(e.hours(), "events.hours"), e.multiplier(), e.label()))
			.toList();
	}

}
