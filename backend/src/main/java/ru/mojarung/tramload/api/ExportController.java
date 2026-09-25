package ru.mojarung.tramload.api;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.function.BiConsumer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.DefaultDataBufferFactory;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import ru.mojarung.tramload.api.dto.ExportRequest;
import ru.mojarung.tramload.application.ExportService;
import ru.mojarung.tramload.application.ExportService.ExportQuery;
import ru.mojarung.tramload.application.ExportService.ExportTable;
import ru.mojarung.tramload.application.Horizon;
import ru.mojarung.tramload.application.Level;
import ru.mojarung.tramload.application.ScenarioService;
import ru.mojarung.tramload.domain.Granularity;
import ru.mojarung.tramload.domain.Scenario;
import ru.mojarung.tramload.domain.ValidationException;

/**
 * Выгрузка прогноза в CSV и XLSX. Файл пишется в поток на виртуальном потоке и уходит клиенту частями
 * по 64 КБ, поток Netty не блокируется, а память не растёт с размером выгрузки.
 */
@RestController
@RequestMapping("/api/v1/export")
@Tag(name = "Выгрузка", description = "Прогноз в CSV (UTF-8 с BOM, «;») и XLSX")
public class ExportController {

	static final MediaType CSV = new MediaType("text", "csv", StandardCharsets.UTF_8);
	static final MediaType XLSX = MediaType
		.parseMediaType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
	private static final int CHUNK = 1 << 16;

	private final ExportService exports;
	private final ScenarioService scenarios;
	private final ExecutorService executor;

	public ExportController(ExportService exports, ScenarioService scenarios,
			@Qualifier("exportExecutor") ExecutorService executor) {
		this.exports = exports;
		this.scenarios = scenarios;
		this.executor = executor;
	}

	@GetMapping
	@Operation(summary = "Выгрузка прогноза по умолчанию",
			description = "level=route|stop|network, ids через запятую (пусто - все объекты уровня). "
					+ "Маршруты по часам за весь горизонт совпадают с сабмитом.")
	public Mono<ResponseEntity<Flux<DataBuffer>>> export(
			@Parameter(description = "csv или xlsx") @RequestParam(defaultValue = "csv") String format,
			@Parameter(example = "route") @RequestParam(defaultValue = "route") String level,
			@Parameter(description = "id через запятую", example = "17,25") @RequestParam(required = false) String ids,
			@RequestParam(required = false) String from, @RequestParam(required = false) String to,
			@RequestParam(required = false) String hours, @RequestParam(required = false) String granularity,
			@RequestParam(required = false) String horizon) {
		return Mono.fromCallable(() -> {
			ExportQuery query = query(level, ids, from, to, hours, granularity, horizon);
			return file(format, exports.table(query, scenarios.defaultScenario()));
		});
	}

	@PostMapping
	@Operation(summary = "Выгрузка прогноза по сценарию")
	public Mono<ResponseEntity<Flux<DataBuffer>>> exportScenario(@RequestBody ExportRequest r) {
		return Mono.fromCallable(() -> {
			ExportQuery query = query(r.level(), r.ids() == null ? null : String.join(",", r.ids()), r.from(), r.to(),
					r.hours(), r.granularity(), r.horizon());
			Scenario scenario = scenarios.resolve(r.coefficients(), Requests.events(r.events()));
			return file(r.format(), exports.table(query, scenario));
		});
	}

	private ResponseEntity<Flux<DataBuffer>> file(String format, ExportTable table) {
		boolean xlsx = "xlsx".equalsIgnoreCase(format);
		if (!xlsx && !"csv".equalsIgnoreCase(format)) {
			throw ValidationException.of("format", "поддерживаются csv и xlsx");
		}
		BiConsumer<ExportTable, java.io.OutputStream> writer = xlsx ? TableWriters::xlsx : TableWriters::csv;
		Flux<DataBuffer> body = Flux.from(DataBufferUtils.outputStreamPublisher(out -> writer.accept(table, out),
				DefaultDataBufferFactory.sharedInstance, executor, CHUNK));
		ContentDisposition disposition = ContentDisposition.attachment()
			.filename(table.fileBaseName() + (xlsx ? ".xlsx" : ".csv"), StandardCharsets.UTF_8)
			.build();
		return ResponseEntity.ok()
			.contentType(xlsx ? XLSX : CSV)
			.header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
			.header("X-Rows", Long.toString(table.rowCount()))
			.body(body);
	}

	private static ExportQuery query(String level, String ids, String from, String to, String hours,
			String granularity, String horizon) {
		List<String> idList = ids == null || ids.isBlank() ? List.of()
				: Arrays.stream(ids.split(",")).map(String::trim).filter(s -> !s.isEmpty()).toList();
		return new ExportQuery(Params.enumValue(level, Level.class, "level"), idList, Params.date(from, "from"),
				Params.date(to, "to"), Params.hours(hours, "hours"),
				Params.enumValue(granularity, Granularity.class, "granularity"),
				Params.enumValue(horizon, Horizon.class, "horizon"));
	}

}
