package ru.mojarung.tramload.api;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DefaultDataBufferFactory;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import reactor.core.publisher.Mono;
import ru.mojarung.tramload.api.dto.NetworkLoadRequest;
import ru.mojarung.tramload.api.dto.NetworkLoadResponse;
import ru.mojarung.tramload.api.dto.SeriesDto;
import ru.mojarung.tramload.application.NetworkLoadService;
import ru.mojarung.tramload.application.NetworkLoadService.NetworkLoad;
import ru.mojarung.tramload.application.NetworkLoadService.Series;
import ru.mojarung.tramload.application.ScenarioService;
import ru.mojarung.tramload.domain.ForecastModel;
import ru.mojarung.tramload.domain.Scenario;
import ru.mojarung.tramload.domain.ValidationException;

/** Карта: трассы и остановки в GeoJSON и нагрузка сети по часам для тепловой карты. */
@RestController
@RequestMapping("/api/v1/network")
@Tag(name = "Карта", description = "Сеть маршрутов и тепловая карта посадок по часам")
public class NetworkController {

	static final MediaType GEO_JSON = new MediaType("application", "geo+json");

	private final ForecastModel model;
	private final NetworkLoadService loads;
	private final ScenarioService scenarios;
	private final String etag;

	public NetworkController(ForecastModel model, NetworkLoadService loads, ScenarioService scenarios) {
		this.model = model;
		this.loads = loads;
		this.scenarios = scenarios;
		this.etag = etag(model, "network");
	}

	@GetMapping
	@Operation(summary = "Трассы по направлениям и остановки (GeoJSON, OSM и справочник организаторов)")
	public Mono<ResponseEntity<DataBuffer>> network(ServerWebExchange exchange) {
		return staticJson(exchange, etag, model.networkGeoJson(), GEO_JSON);
	}

	/** Внешние факторы отдаются тем же способом, что и сеть: байты как есть, ETag по версии артефактов. */
	static Mono<ResponseEntity<DataBuffer>> staticJson(ServerWebExchange exchange, String etag,
			java.nio.ByteBuffer bytes, MediaType type) {
		if (exchange.checkNotModified(etag)) {
			return Mono.just(ResponseEntity.status(304).eTag(etag).build());
		}
		return Mono.just(ResponseEntity.ok().eTag(etag).cacheControl(ReferenceController.STATIC).contentType(type)
			.body(DefaultDataBufferFactory.sharedInstance.wrap(bytes)));
	}

	@GetMapping("/load")
	@Operation(summary = "Посадки маршрутов и остановок по часам даты: кадры тепловой карты")
	public Mono<NetworkLoadResponse> load(@Parameter(example = "2025-11-03") @RequestParam(required = false) String date,
			@Parameter(description = "окно часов", example = "6-23") @RequestParam(required = false) String hours) {
		return Mono.fromCallable(() -> view(
				loads.load(Params.date(date, "date"), Params.hours(hours, "hours"), scenarios.defaultScenario()), false));
	}

	@PostMapping("/load")
	@Operation(summary = "Кадры тепловой карты по сценарию")
	public Mono<NetworkLoadResponse> loadScenario(@RequestBody NetworkLoadRequest request) {
		return Mono.fromCallable(() -> {
			if (request == null) {
				throw ValidationException.of("body", "пустой запрос");
			}
			Scenario scenario = scenarios.resolve(request.coefficients(), Requests.events(request.events()));
			return view(loads.load(Params.date(request.date(), "date"), Params.hours(request.hours(), "hours"), scenario),
					true);
		});
	}

	static String etag(ForecastModel model, String name) {
		return "\"" + name + "-" + model.info().gitCommit() + "-" + model.info().generatedAt() + "\"";
	}

	private static NetworkLoadResponse view(NetworkLoad load, boolean scenario) {
		return new NetworkLoadResponse(load.date(), load.hours(), Views.TIMEZONE, scenario,
				load.routes().stream().map(NetworkController::series).toList(),
				load.stops().stream().map(NetworkController::series).toList());
	}

	private static SeriesDto series(Series s) {
		return new SeriesDto(s.id(), s.values().stream().map(Views::round).toList());
	}

}
