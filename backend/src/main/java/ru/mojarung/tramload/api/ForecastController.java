package ru.mojarung.tramload.api;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import reactor.core.publisher.Mono;
import ru.mojarung.tramload.api.dto.ExplainRequest;
import ru.mojarung.tramload.api.dto.ExplainResponse;
import ru.mojarung.tramload.api.dto.ForecastQueryDto;
import ru.mojarung.tramload.api.dto.ForecastResponse;
import ru.mojarung.tramload.api.dto.ScenarioRequest;
import ru.mojarung.tramload.api.dto.ScenarioResponse;
import ru.mojarung.tramload.application.ForecastService;
import ru.mojarung.tramload.application.ScenarioService;
import ru.mojarung.tramload.domain.ForecastEngine;
import ru.mojarung.tramload.domain.Scenario;
import ru.mojarung.tramload.domain.ValidationException;

/**
 * Прогноз посадок по маршруту, остановке, участку или сети. Расчёт занимает микросекунды и идёт прямо
 * на потоке Netty: блокирующих вызовов в нём нет, данные уже в памяти.
 */
@RestController
@RequestMapping("/api/v1/forecast")
@Tag(name = "Прогноз", description = "Ряды посадок по объекту, интервалу и горизонту")
public class ForecastController {

	private final ForecastService forecasts;
	private final ScenarioService scenarios;

	public ForecastController(ForecastService forecasts, ScenarioService scenarios) {
		this.forecasts = forecasts;
		this.scenarios = scenarios;
	}

	@GetMapping
	@Operation(summary = "Прогноз по умолчанию",
			description = "Горизонт day - сутки по часам, month - месяц по дням, year - 12 месяцев от месяца from (без from: ноябрь 2025 - октябрь 2026) по "
					+ "месяцам. Без горизонта ряд строится от from до to с шагом granularity.")
	public Mono<ForecastResponse> forecast(
			@Parameter(description = "route, stop, segment или network", example = "route") @RequestParam(
					required = false) String level,
			@Parameter(description = "маршрут (route, segment) или id остановки (stop)", example = "17") @RequestParam(
					required = false) String id,
			@RequestParam(required = false) Integer direction, @RequestParam(required = false) String fromStop,
			@RequestParam(required = false) String toStop,
			@Parameter(example = "2025-11-03") @RequestParam(required = false) String from,
			@Parameter(example = "2025-11-03") @RequestParam(required = false) String to,
			@Parameter(description = "окно часов", example = "7-9") @RequestParam(required = false) String hours,
			@Parameter(description = "hour, day, month") @RequestParam(required = false) String granularity,
			@Parameter(description = "day, week, month, year") @RequestParam(required = false) String horizon) {
		ForecastQueryDto dto = new ForecastQueryDto(level, id, direction, fromStop, toStop, from, to, hours, granularity,
				horizon);
		return Mono.fromCallable(() -> Views.forecast(forecasts.forecast(Requests.query(dto))));
	}

	@GetMapping("/explain")
	@Operation(summary = "Из чего сложился прогноз",
			description = "Посадки маршрута или сети за сутки после каждого шага формулы: профиль последних недель, "
					+ "уровень месяца, календарь, события сети, погода, поправка до v11, события сценария.")
	public Mono<ExplainResponse> explain(
			@Parameter(description = "маршрут; без него - вся сеть", example = "17") @RequestParam(
					required = false) Integer route,
			@Parameter(example = "2025-11-18") @RequestParam String date) {
		return Mono.fromCallable(() -> explanation(route, date, scenarios.defaultScenario()));
	}

	@PostMapping("/explain")
	@Operation(summary = "Из чего сложился прогноз сценария",
			description = "То же, что GET /explain, но с ползунками и событиями сценария.")
	public Mono<ExplainResponse> explainScenario(@RequestBody ExplainRequest request) {
		return Mono.fromCallable(() -> {
			if (request == null) {
				throw ValidationException.of("body", "пустой запрос");
			}
			Scenario scenario = scenarios.resolve(request.coefficients(), Requests.events(request.events()));
			return explanation(request.route(), request.date(), scenario);
		});
	}

	private ExplainResponse explanation(Integer route, String date, Scenario scenario) {
		var day = Params.date(date, "date");
		if (day == null) {
			throw ValidationException.of("date", "нужна дата, например 2025-11-18");
		}
		ForecastEngine.Explanation e = scenarios.explain(scenario, route, day);
		var steps = new java.util.ArrayList<ExplainResponse.Step>();
		for (int i = 0; i < e.totals().length; i++) {
			double delta = i == 0 ? e.totals()[0] : e.totals()[i] - e.totals()[i - 1];
			steps.add(new ExplainResponse.Step(ForecastEngine.Explanation.STEPS.get(i), e.totals()[i], delta));
		}
		return new ExplainResponse(route, day.toString(), steps);
	}

	@PostMapping("/scenario")
	@Operation(summary = "Пересчёт по сценарию",
			description = "Ползунки из /api/v1/coefficients и события. Возвращает ряд сценария, базовый ряд и разницу. "
					+ "Одинаковые сценарии берутся из кэша.")
	public Mono<ScenarioResponse> scenario(@RequestBody ScenarioRequest request) {
		return Mono.fromCallable(() -> {
			if (request == null) {
				throw ValidationException.of("body", "пустой запрос");
			}
			var scenario = scenarios.resolve(request.coefficients(), Requests.events(request.events()));
			return Views.scenario(forecasts.compare(Requests.query(request.query()), scenario));
		});
	}

}
