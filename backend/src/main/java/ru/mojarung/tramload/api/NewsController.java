package ru.mojarung.tramload.api;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import ru.mojarung.tramload.api.dto.EventDto;
import ru.mojarung.tramload.api.dto.IncidentDto;
import ru.mojarung.tramload.api.dto.NewsFeedDto;
import ru.mojarung.tramload.application.NewsService;
import ru.mojarung.tramload.domain.news.Incident;

/** Сбои из оперативных новостей Дептранса, превращённые в события сценария. */
@RestController
@RequestMapping("/api/v1/news")
@Tag(name = "Новости", description = "Сбои движения из канала Дептранса как события сценария")
public class NewsController {

	private final NewsService news;

	public NewsController(NewsService news) {
		this.news = news;
	}

	/** Живая лента - сетевой вызов, поэтому ответ собирается вне потоков Netty. */
	@GetMapping
	@Operation(summary = "Сбои трамваев: проверенный архив 2025 года и свежие сообщения канала t.me/DtOperativno")
	public Mono<NewsFeedDto> feed() {
		return Mono.fromCallable(news::feed).subscribeOn(Schedulers.boundedElastic()).map(f -> new NewsFeedDto(
				f.items().stream().map(NewsController::incident).toList(), f.alpha(), f.alphaSource(),
				f.liveCheckedAt().map(Object::toString).orElse(null), f.liveError().orElse(null)));
	}

	@GetMapping("/{id}/events")
	@Operation(summary = "События сценария, если такой же сбой случится в выбранный день прогноза")
	public Mono<List<EventDto>> tryOn(@PathVariable String id, @RequestParam String date) {
		return Mono.fromCallable(() -> news.tryOn(id, Params.date(date, "date")).stream().map(Views::event).toList())
			.subscribeOn(Schedulers.boundedElastic());
	}

	private static IncidentDto incident(NewsService.Item item) {
		Incident i = item.incident();
		return new IncidentDto(i.id(), i.routes(), i.start().toString(), i.end().map(Object::toString).orElse(null),
				i.minutes().map(m -> Math.round(m * 10) / 10.0).orElse(null), i.cause().code(), i.cause().label(),
				i.location(), i.sourceUrl(), i.recoveryUrl().orElse(null), item.inForecast(),
				i.origin().name().toLowerCase(java.util.Locale.ROOT), item.events().stream().map(Views::event).toList());
	}

}
