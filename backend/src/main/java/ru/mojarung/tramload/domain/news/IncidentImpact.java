package ru.mojarung.tramload.domain.news;

import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.OptionalInt;

import ru.mojarung.tramload.domain.HourWindow;
import ru.mojarung.tramload.domain.ScenarioEvent;

/**
 * Сбой как события сценария. В каждом часе под сбоем посадки маршрута умножаются на 1 - alpha × доля
 * часа под сбоем: полный час остановки при alpha 0,5 - половина посадок. Соседние часы с одним множителем
 * склеиваются в одно окно. Сбой можно «примерить» на другой день: часы и длительность те же.
 */
public final class IncidentImpact {

	public static final ZoneOffset MOSCOW = ZoneOffset.ofHours(3);
	private static final DateTimeFormatter DAY = DateTimeFormatter.ofPattern("dd.MM");
	private static final double MINUTES_PER_HOUR = 60.0;

	private IncidentImpact() {
	}

	/** События на тот же день, когда был сбой. */
	public static List<ScenarioEvent> events(Incident incident, double alpha) {
		return events(incident, alpha, incident.start().withOffsetSameInstant(MOSCOW).toLocalDate());
	}

	/** События, если такой же сбой случится в день on: те же часы, та же длительность. */
	public static List<ScenarioEvent> events(Incident incident, double alpha, LocalDate on) {
		if (incident.end().isEmpty()) {
			return List.of();
		}
		LocalDateTime start = incident.start().withOffsetSameInstant(MOSCOW).toLocalDateTime();
		LocalDateTime end = incident.end().get().withOffsetSameInstant(MOSCOW).toLocalDateTime();
		long shift = ChronoUnit.DAYS.between(start.toLocalDate(), on);
		String label = label(incident, shift != 0);
		List<Window> windows = new ArrayList<>();
		for (LocalDateTime h = start.truncatedTo(ChronoUnit.HOURS); h.isBefore(end); h = h.plusHours(1)) {
			LocalDateTime from = h.isAfter(start) ? h : start;
			LocalDateTime to = h.plusHours(1).isBefore(end) ? h.plusHours(1) : end;
			double exposure = Duration.between(from, to).toSeconds() / 60.0 / MINUTES_PER_HOUR;
			double multiplier = Math.round((1 - alpha * exposure) * 1000) / 1000.0;
			LocalDate date = h.toLocalDate().plusDays(shift);
			Window last = windows.isEmpty() ? null : windows.getLast();
			if (last != null && last.date.equals(date) && last.last == h.getHour() - 1 && last.multiplier == multiplier) {
				windows.set(windows.size() - 1, new Window(date, last.first, h.getHour(), multiplier));
			}
			else {
				windows.add(new Window(date, h.getHour(), h.getHour(), multiplier));
			}
		}
		List<ScenarioEvent> events = new ArrayList<>();
		for (int route : incident.routes()) {
			for (Window w : windows) {
				events.add(new ScenarioEvent(OptionalInt.of(route), w.date, w.date, new HourWindow(w.first, w.last),
						w.multiplier, label));
			}
		}
		return events;
	}

	/** «сбой 08.11: технические причины» или «как сбой 08.11: ДТП», если сбой перенесён на другой день. */
	static String label(Incident incident, boolean moved) {
		String day = incident.start().withOffsetSameInstant(MOSCOW).format(DAY);
		return (moved ? "как сбой " : "сбой ") + day + ": " + incident.cause().label();
	}

	private record Window(LocalDate date, int first, int last, double multiplier) {
	}

}
