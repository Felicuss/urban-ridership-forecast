package ru.mojarung.tramload.application;

import java.time.Instant;
import java.time.LocalDate;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import ru.mojarung.tramload.domain.ForecastGrid;
import ru.mojarung.tramload.domain.ScenarioEvent;
import ru.mojarung.tramload.domain.ValidationException;
import ru.mojarung.tramload.domain.news.Incident;
import ru.mojarung.tramload.domain.news.IncidentImpact;
import ru.mojarung.tramload.domain.news.NewsArchive;
import ru.mojarung.tramload.domain.news.NewsSource;
import ru.mojarung.tramload.domain.news.NewsSource.LiveNews;

/**
 * Сбои из новостей Дептранса как события сценария. Архив 2025 года проверен вручную, живая лента канала
 * разбирается автоматически по тем же правилам. Сбой в горизонте прогноза уже учтён в прогнозе v11, поэтому
 * его события показываются для справки; любой сбой можно примерить на выбранный день горизонта.
 */
public final class NewsService {

	private final NewsArchive archive;
	private final NewsSource live;
	private final ForecastGrid grid;

	public NewsService(NewsArchive archive, NewsSource live, ForecastGrid grid) {
		this.archive = archive;
		this.live = live;
		this.grid = grid;
	}

	/**
	 * Сбой с событиями сценария на его собственный день.
	 *
	 * @param inForecast день сбоя в горизонте прогноза: сбой уже учтён в прогнозе по умолчанию
	 */
	public record Item(Incident incident, boolean inForecast, List<ScenarioEvent> events) {
	}

	public record Feed(List<Item> items, double alpha, String alphaSource, Optional<Instant> liveCheckedAt,
			Optional<String> liveError) {
	}

	/** Все сбои, свежие сверху: живая лента и архив; при совпадении номера остаётся проверенный архив. */
	public Feed feed() {
		LiveNews fresh = live.latest();
		Map<String, Incident> byId = new LinkedHashMap<>();
		fresh.incidents().forEach(i -> byId.put(i.id(), i));
		archive.incidents().forEach(i -> byId.put(i.id(), i));
		List<Item> items = byId.values()
			.stream()
			.sorted(Comparator.comparing(Incident::start).reversed())
			.map(this::item)
			.toList();
		return new Feed(items, archive.alpha(), archive.alphaSource(), fresh.checkedAt(), fresh.error());
	}

	/** События, если такой же сбой случится в день date горизонта прогноза. */
	public List<ScenarioEvent> tryOn(String id, LocalDate date) {
		if (date == null || !grid.contains(date)) {
			throw ValidationException.of("date", "примерить сбой можно на день прогноза: " + grid.start() + " - " + grid.end());
		}
		Incident incident = find(id);
		if (incident.ongoing()) {
			throw ValidationException.of("id", "движение ещё не восстановлено: длительность сбоя неизвестна");
		}
		return inGrid(IncidentImpact.events(incident, archive.alpha(), date));
	}

	private Incident find(String id) {
		Optional<Incident> known = archive.incidents().stream().filter(i -> i.id().equals(id)).findFirst();
		return known.or(() -> live.latest().incidents().stream().filter(i -> i.id().equals(id)).findFirst())
			.orElseThrow(() -> ValidationException.of("id", "сбоя " + id + " нет ни в архиве, ни в свежей ленте"));
	}

	private Item item(Incident incident) {
		LocalDate day = incident.start().withOffsetSameInstant(IncidentImpact.MOSCOW).toLocalDate();
		boolean inForecast = grid.contains(day);
		List<ScenarioEvent> events = inForecast ? inGrid(IncidentImpact.events(incident, archive.alpha())) : List.of();
		return new Item(incident, inForecast, events);
	}

	/** Ночной сбой в последний день горизонта заходит за его конец: эти часы прогноз не считает. */
	private List<ScenarioEvent> inGrid(List<ScenarioEvent> events) {
		return events.stream().filter(e -> grid.contains(e.from())).toList();
	}

}
