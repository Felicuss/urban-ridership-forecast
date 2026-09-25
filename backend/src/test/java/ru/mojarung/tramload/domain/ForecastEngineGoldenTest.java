package ru.mojarung.tramload.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import tools.jackson.databind.json.JsonMapper;

import ru.mojarung.tramload.TestArtifacts;

/**
 * Эталон: формула сервиса совпадает с лучшим сабмитом v6 (0.90553) во всех 14 640 ячейках и с исходной
 * реализацией на Python (s10.make_forecast × множитель до v6) на пяти наборах коэффициентов из artifacts/golden/.
 */
class ForecastEngineGoldenTest {

	private static final ForecastModel MODEL = TestArtifacts.model();
	private static final ForecastEngine ENGINE = new ForecastEngine(MODEL.components(), MODEL.constants());

	@Test
	void defaultScenarioReproducesBestSubmissionInEveryCell() throws IOException {
		Path submission = TestArtifacts.repoRoot().resolve(MODEL.info().defaultSubmission());
		List<String> lines = Files.readAllLines(submission, StandardCharsets.UTF_8);
		double[] prediction = ENGINE.compute(Scenario.of(MODEL.catalog().defaults()));
		ForecastGrid grid = MODEL.grid();

		assertThat(lines).hasSize(grid.size() + 1);
		for (String line : lines.subList(1, lines.size())) {
			String[] f = line.split(";");
			int cell = grid.cell(grid.routeIndex(Integer.parseInt(f[0])), grid.dayIndex(LocalDate.parse(f[1])),
					Integer.parseInt(f[2]));
			assertThat((long) Math.rint(prediction[cell])).as(line).isEqualTo(Long.parseLong(f[3]));
		}
	}

	@ParameterizedTest
	@MethodSource("goldenScenarios")
	void formulaMatchesPythonRulesWhenCoefficientsMove(String name, Map<String, Object> overrides) throws IOException {
		double[] expected = goldenColumn(name);

		double[] actual = ENGINE.compute(Scenario.of(MODEL.catalog().resolve(overrides)));

		for (int cell = 0; cell < expected.length; cell++) {
			assertThat(actual[cell]).as("%s, ячейка %d", name, cell)
				.isCloseTo(expected[cell], within(1e-9 * Math.max(1.0, Math.abs(expected[cell]))));
		}
	}

	@SuppressWarnings("unchecked")
	static Stream<Object[]> goldenScenarios() throws IOException {
		Map<String, Map<String, Object>> sets = JsonMapper.builder().build()
			.readValue(Files.readAllBytes(TestArtifacts.dir().resolve("golden/scenarios.json")), Map.class);
		return sets.entrySet().stream().map(e -> new Object[] { e.getKey(), e.getValue() });
	}

	/** Столбец сценария из golden/scenarios.csv, разложенный по индексам ячеек сетки. */
	private static double[] goldenColumn(String name) throws IOException {
		List<String> lines = Files.readAllLines(TestArtifacts.dir().resolve("golden/scenarios.csv"));
		int column = List.of(lines.getFirst().split(",")).indexOf(name);
		ForecastGrid grid = MODEL.grid();
		double[] out = new double[grid.size()];
		for (String line : lines.subList(1, lines.size())) {
			String[] f = line.split(",");
			int cell = grid.cell(grid.routeIndex(Integer.parseInt(f[0])), grid.dayIndex(LocalDate.parse(f[1])),
					Integer.parseInt(f[2]));
			out[cell] = Double.parseDouble(f[column]);
		}
		return out;
	}

}
