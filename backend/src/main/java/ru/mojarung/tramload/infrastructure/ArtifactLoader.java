package ru.mojarung.tramload.infrastructure;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

import ru.mojarung.tramload.domain.CellComponents;
import ru.mojarung.tramload.domain.DayKind;
import ru.mojarung.tramload.domain.ForecastComponents;
import ru.mojarung.tramload.domain.ForecastGrid;
import ru.mojarung.tramload.domain.ForecastModel;
import ru.mojarung.tramload.domain.Intervals;
import ru.mojarung.tramload.domain.ModelConstants;
import ru.mojarung.tramload.domain.ModelInfo;
import ru.mojarung.tramload.domain.YearForecast;
import ru.mojarung.tramload.domain.coefficient.CoefficientCatalog;
import ru.mojarung.tramload.domain.network.RouteStop;
import ru.mojarung.tramload.domain.network.Stop;
import ru.mojarung.tramload.domain.network.StopNetwork;

/**
 * Читает artifacts/ (контракт - analysis/s40_export_artifacts.py) в неизменяемую {@link ForecastModel}.
 * Сначала сверяет файлы с manifest.json, потом разбирает. Любая ошибка - {@link ArtifactValidationException}.
 */
public final class ArtifactLoader {

	private static final JsonMapper JSON = JsonMapper.builder().build();

	public ForecastModel load(Path dir) {
		JsonNode manifest = readJson(dir.resolve("manifest.json"));
		ManifestVerifier.verify(dir, manifest);
		ForecastGrid grid = grid(manifest);
		JsonNode coefficients = readJson(dir.resolve("coefficients.json"));
		try {
			return new ForecastModel(components(dir, grid), constants(coefficients),
					new CoefficientCatalog(CatalogParser.specs(coefficients)), network(dir),
					intervals(readJson(dir.resolve("intervals.json"))), year(dir), info(dir, manifest),
					ByteBuffer.wrap(Files.readAllBytes(dir.resolve("network.geojson"))));
		}
		catch (IOException | IllegalArgumentException | ClassCastException ex) {
			throw new ArtifactValidationException("artifacts/ не разобраны: " + ex.getMessage(), ex);
		}
	}

	static JsonNode readJson(Path path) {
		if (!Files.isRegularFile(path)) {
			throw new ArtifactValidationException("нет файла " + path.toAbsolutePath());
		}
		try {
			return JSON.readTree(Files.readAllBytes(path));
		}
		catch (IOException | RuntimeException ex) {
			throw new ArtifactValidationException("не удалось прочитать " + path.getFileName() + ": " + ex.getMessage(),
					ex);
		}
	}

	private static ForecastGrid grid(JsonNode manifest) {
		List<Integer> routes = new ArrayList<>();
		manifest.path("routes").forEach(r -> routes.add(r.asInt()));
		LocalDate from = LocalDate.parse(manifest.path("horizon").path("from").asString());
		LocalDate to = LocalDate.parse(manifest.path("horizon").path("to").asString());
		return new ForecastGrid(routes, from, (int) ChronoUnit.DAYS.between(from, to) + 1);
	}

	private static ForecastComponents components(Path dir, ForecastGrid grid) {
		List<CellComponents> cells = CsvRows.read(dir.resolve("forecast_components.csv")).stream()
			.map(ArtifactLoader::cell)
			.toList();
		return ForecastComponents.of(grid, cells);
	}

	private static CellComponents cell(Map<String, String> r) {
		return new CellComponents(CsvRows.integer(r, "route"), LocalDate.parse(CsvRows.required(r, "date")),
				CsvRows.integer(r, "hour"), CsvRows.integer(r, "dow"), DayKind.parse(CsvRows.required(r, "kind")),
				CsvRows.flag(r, "is_holiday"), CsvRows.flag(r, "is_working_saturday"), CsvRows.flag(r, "is_pre_new_year"),
				CsvRows.flag(r, "is_new_year_eve"), CsvRows.number(r, "base"), CsvRows.number(r, "base_restored"),
				CsvRows.flag(r, "restorable"), CsvRows.number(r, "route5_shape"), CsvRows.number(r, "precip_day"),
				CsvRows.number(r, "precip_hour"), CsvRows.number(r, "temp_day"), CsvRows.number(r, "prediction"));
	}

	private static ModelConstants constants(JsonNode coefficients) {
		JsonNode c = coefficients.path("constants");
		return new ModelConstants(c.path("traffic_level_nov").asDouble(), c.path("traffic_level_dec").asDouble(),
				c.path("route5_saturday_ratio").asDouble(), c.path("route5_sunday_ratio").asDouble());
	}

	private static StopNetwork network(Path dir) {
		List<Stop> stops = CsvRows.read(dir.resolve("stops.csv")).stream()
			.map(r -> new Stop(CsvRows.required(r, "stop_id"), CsvRows.required(r, "name"), CsvRows.number(r, "lat"),
					CsvRows.number(r, "lon"), CsvRows.required(r, "source"),
					Arrays.stream(CsvRows.required(r, "routes").split(" ")).map(Integer::parseInt).toList()))
			.toList();
		List<RouteStop> routeStops = CsvRows.read(dir.resolve("route_stops.csv")).stream()
			.map(r -> new RouteStop(CsvRows.integer(r, "route"), CsvRows.integer(r, "direction"),
					CsvRows.integer(r, "seq"), CsvRows.required(r, "stop_id"), CsvRows.number(r, "share")))
			.toList();
		return new StopNetwork(stops, routeStops);
	}

	private static Intervals intervals(JsonNode node) {
		double[][] byHour = new double[ForecastGrid.HOURS][];
		for (int h = 0; h < ForecastGrid.HOURS; h++) {
			byHour[h] = pair(node.path("hour").path("factors").path(String.valueOf(h)));
		}
		Map<DayKind, double[]> byKind = new EnumMap<>(DayKind.class);
		for (DayKind kind : DayKind.values()) {
			byKind.put(kind, pair(node.path("day").path("factors").path(kind.code())));
		}
		return new Intervals(byHour, byKind, pair(node.path("month").path("factors").path("all")));
	}

	private static double[] pair(JsonNode node) {
		if (!node.isArray() || node.size() != 2) {
			throw new ArtifactValidationException("intervals.json: ожидается пара множителей, получено " + node);
		}
		return new double[] { node.get(0).asDouble(), node.get(1).asDouble() };
	}

	private static YearForecast year(Path dir) {
		return new YearForecast(CsvRows.read(dir.resolve("forecast_year.csv")).stream()
			.map(r -> new YearForecast.Row(CsvRows.integer(r, "route"), YearMonth.parse(CsvRows.required(r, "month")),
					CsvRows.number(r, "p50"), CsvRows.number(r, "p10"), CsvRows.number(r, "p90"),
					CsvRows.required(r, "method")))
			.toList());
	}

	@SuppressWarnings("unchecked")
	private static ModelInfo info(Path dir, JsonNode manifest) throws IOException {
		Map<String, Object> metrics = JSON.readValue(Files.readAllBytes(dir.resolve("backtest_metrics.json")), Map.class);
		JsonNode scenario = manifest.path("default_scenario");
		return new ModelInfo(manifest.path("model_version").asString(), manifest.path("git_commit").asString(),
				manifest.path("generated_at").asString(), LocalDate.parse(manifest.path("forecast_origin").asString()),
				scenario.path("leaderboard_wape_score").asDouble(), scenario.path("submission").asString(), metrics);
	}

}
