package ru.mojarung.tramload.domain.news;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;

/**
 * Сбой движения трамваев из оперативного канала Дептранса: сообщение «задерживаются трамваи №…» и ответ
 * «восстановлено движение». Начало и конец - время публикации сообщений, а не телеметрия. Пока ответа нет,
 * конца нет: длительность не выдумывается.
 */
public record Incident(String id, List<Integer> routes, OffsetDateTime start, Optional<OffsetDateTime> end,
		IncidentCause cause, String location, String sourceUrl, Optional<String> recoveryUrl, Origin origin) {

	/** Откуда сбой: архив 2025 года, проверенный вручную, или живая лента канала. */
	public enum Origin {
		ARCHIVE, LIVE
	}

	public Incident {
		routes = List.copyOf(routes);
		if (routes.isEmpty()) {
			throw new IllegalArgumentException("сбой " + id + " без маршрутов");
		}
		if (end.isPresent() && !end.get().isAfter(start)) {
			throw new IllegalArgumentException("сбой " + id + ": конец не позже начала");
		}
	}

	public boolean ongoing() {
		return end.isEmpty();
	}

	/** Длительность в минутах; пусто, пока движение не восстановлено. */
	public Optional<Double> minutes() {
		return end.map(e -> Duration.between(start, e).toSeconds() / 60.0);
	}

}
