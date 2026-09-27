package ru.mojarung.tramload.api;

import java.time.Duration;
import java.util.List;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import reactor.core.publisher.Mono;
import ru.mojarung.tramload.api.dto.CalendarDayDto;
import ru.mojarung.tramload.api.dto.CoefficientDto;
import ru.mojarung.tramload.api.dto.MetaResponse;
import ru.mojarung.tramload.api.dto.RouteDto;
import ru.mojarung.tramload.api.dto.RouteStopDto;
import ru.mojarung.tramload.api.dto.StopDto;
import ru.mojarung.tramload.application.ScenarioService;
import ru.mojarung.tramload.domain.ForecastGrid;
import ru.mojarung.tramload.domain.ForecastModel;
import ru.mojarung.tramload.domain.ModelInfo;
import ru.mojarung.tramload.domain.ValidationException;
import ru.mojarung.tramload.domain.network.Stop;

/** Справочные данные: паспорт модели, ползунки, маршруты и остановки. Меняются только с новыми артефактами. */
@RestController
@RequestMapping("/api/v1")
@Tag(name = "Справочники", description = "Модель, ползунки, маршруты и остановки")
public class ReferenceController {

	static final CacheControl STATIC = CacheControl.maxAge(Duration.ofHours(1)).cachePublic();
	private static final List<String> APPLICABILITY = List.of(
			"Почасовой прогноз: 1 ноября - 31 декабря 2025, построен по данным до 31 октября 2025",
			"Январь-октябрь 2025: факт, успешные валидации из данных организаторов",
			"2026–2027 годы: сезонная оценка без тренда роста, условный коридор ±12 %; точность 2027 не проверена",
			"Маршруты 1, 5, 7, 11, 12, 17, 25, 26, 28, 50; новый маршрут, перекрытие или изменение трассы "
					+ "задаются событием на вкладке «Сценарий»",
			"Точность считается по маршруту и часу; для остановок и участков прогноз маршрута делится "
					+ "по долям остановок");

	private final ForecastModel model;
	private final ScenarioService scenarios;
	private final String factorsEtag;

	public ReferenceController(ForecastModel model, ScenarioService scenarios) {
		this.model = model;
		this.scenarios = scenarios;
		this.factorsEtag = NetworkController.etag(model, "factors");
	}

	@GetMapping("/meta")
	@Operation(summary = "Паспорт модели: версия, горизонт, качество на лидерборде и бэктесте")
	public ResponseEntity<MetaResponse> meta() {
		ModelInfo info = model.info();
		ForecastGrid grid = model.grid();
		return ResponseEntity.ok().cacheControl(STATIC).body(new MetaResponse(info.modelVersion(), info.gitCommit(),
				info.generatedAt(), info.forecastOrigin(), grid.start(), grid.end(), model.timeline().start(),
				model.timeline().end(), grid.routes(), Views.TIMEZONE,
				info.leaderboardWapeScore(), info.defaultSubmission(), info.metrics(), APPLICABILITY));
	}

	@GetMapping("/factors")
	@Operation(summary = "Внешние факторы: календарь, погода по часам, загруженность дорог, пассажиропоток города, "
			+ "интервалы движения по расписанию, посадки по дням за январь-октябрь 2025, события сети")
	public Mono<ResponseEntity<DataBuffer>> factors(ServerWebExchange exchange) {
		return NetworkController.staticJson(exchange, factorsEtag, model.factorsJson(), MediaType.APPLICATION_JSON);
	}

	@GetMapping("/calendar")
	@Operation(summary = "Календарь шкалы: тип дня, праздник и источник данных (fact, forecast, outlook) на каждый день")
	public ResponseEntity<List<CalendarDayDto>> calendar() {
		List<CalendarDayDto> days = model.timeline().days().stream()
			.map(d -> new CalendarDayDto(d.date(), d.dayOfWeek(), d.dayType(), d.kind().code(), d.dayOff(), d.holiday(),
					d.source().code()))
			.toList();
		return ResponseEntity.ok().cacheControl(STATIC).body(days);
	}

	@GetMapping("/coefficients")
	@Operation(summary = "Ползунки: значение по умолчанию, диапазон, шаг и источник")
	public ResponseEntity<List<CoefficientDto>> coefficients() {
		List<CoefficientDto> items = model.catalog().specs().stream()
			.map(s -> new CoefficientDto(s.key(), s.label(), s.group(), s.type().name().toLowerCase(),
					json(s.defaultValue()), json(s.min()), json(s.max()), s.step(), s.source()))
			.toList();
		return ResponseEntity.ok().cacheControl(STATIC).body(items);
	}

	@GetMapping("/routes")
	@Operation(summary = "Маршруты: число остановок и посадки за горизонт по умолчанию")
	public ResponseEntity<List<RouteDto>> routes() {
		ForecastGrid grid = model.grid();
		double[] prediction = scenarios.defaultPrediction();
		List<RouteDto> routes = grid.routes().stream().map(route -> {
			double total = 0;
			for (int d = 0; d < grid.days(); d++) {
				for (int h = 0; h < ForecastGrid.HOURS; h++) {
					total += prediction[grid.cell(grid.routeIndex(route), d, h)];
				}
			}
			int stops = model.network().routeStops(route).size();
			return new RouteDto(route, stops, Views.round(total), Views.round(total / grid.days()));
		}).toList();
		return ResponseEntity.ok().cacheControl(STATIC).body(routes);
	}

	@GetMapping("/routes/{route}/stops")
	@Operation(summary = "Остановки маршрута по направлениям и доли посадок (оценка)")
	public ResponseEntity<List<RouteStopDto>> routeStops(@PathVariable int route) {
		if (!model.grid().hasRoute(route)) {
			throw ValidationException.of("route", "маршрута " + route + " нет в прогнозе, доступны " + model.grid().routes());
		}
		List<RouteStopDto> stops = model.network().routeStops(route).stream().map(rs -> {
			Stop s = model.network().stop(rs.stopId()).orElseThrow();
			return new RouteStopDto(rs.direction(), rs.seq(), rs.stopId(), s.name(), s.lat(), s.lon(), rs.share());
		}).toList();
		return ResponseEntity.ok().cacheControl(STATIC).body(stops);
	}

	@GetMapping("/stops")
	@Operation(summary = "Все остановки сети с маршрутами")
	public ResponseEntity<List<StopDto>> stops() {
		List<StopDto> stops = model.network().stops().stream()
			.map(s -> new StopDto(s.id(), s.name(), s.lat(), s.lon(), s.source(), s.routes()))
			.toList();
		return ResponseEntity.ok().cacheControl(STATIC).body(stops);
	}

	/** Даты и время отдаём строками ISO-8601, числа и логические значения как есть. */
	private static Object json(Object value) {
		return value instanceof Number || value instanceof Boolean || value == null ? value : value.toString();
	}

}
