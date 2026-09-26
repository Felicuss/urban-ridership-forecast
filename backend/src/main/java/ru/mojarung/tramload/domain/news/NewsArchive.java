package ru.mojarung.tramload.domain.news;

import java.util.List;

/**
 * Сбои 2025 года из artifacts/news.json и оценка их влияния.
 *
 * @param alpha доля посадок, которую маршрут теряет за час полной остановки
 * @param alphaSource откуда оценка: скрипт, число сбоев и часов
 */
public record NewsArchive(String channel, double alpha, String alphaSource, List<Incident> incidents) {

	public NewsArchive {
		if (!(alpha > 0 && alpha <= 1)) {
			throw new IllegalArgumentException("доля потерь за час сбоя вне (0, 1]: " + alpha);
		}
		incidents = List.copyOf(incidents);
	}

}
