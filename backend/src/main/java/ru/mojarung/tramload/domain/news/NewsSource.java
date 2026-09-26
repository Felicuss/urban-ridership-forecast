package ru.mojarung.tramload.domain.news;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

/** Живая лента сбоев: последние сообщения канала, уже разобранные в сбои. */
public interface NewsSource {

	LiveNews latest();

	/**
	 * Результат последней проверки ленты.
	 *
	 * @param checkedAt когда лента читалась; пусто, если живая лента выключена
	 * @param error почему прочитать не удалось; пусто, если всё прочитано
	 */
	record LiveNews(List<Incident> incidents, Optional<Instant> checkedAt, Optional<String> error) {

		public LiveNews {
			incidents = List.copyOf(incidents);
		}

		public static LiveNews off() {
			return new LiveNews(List.of(), Optional.empty(), Optional.empty());
		}

	}

}
