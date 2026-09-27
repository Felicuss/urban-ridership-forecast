package ru.mojarung.tramload.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

import org.dhatim.fastexcel.reader.ReadableWorkbook;
import org.dhatim.fastexcel.reader.Row;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import ru.mojarung.tramload.TestArtifacts;
import ru.mojarung.tramload.domain.network.RouteStop;

/** Выгрузка: формат CSV для Excel, те же числа в XLSX, совпадение с сабмитом и имя файла по RFC 6266. */
@SpringBootTest
@AutoConfigureWebTestClient(timeout = "PT60S")
class ExportTest {

	private static final String ALL_ROUTES_HOURLY = "level=route&from=2025-11-01&to=2025-12-31&granularity=hour";

	private static final int MAX_BODY = 64 * 1024 * 1024;

	WebTestClient client;

	@Autowired
	void setClient(WebTestClient client) {
		// у клиента теста буфер 256 КБ по умолчанию, выгрузка больше
		this.client = client.mutate().codecs(c -> c.defaultCodecs().maxInMemorySize(MAX_BODY)).build();
	}

	@Test
	void csvOfAllRoutesByHourIsTheSubmissionWithBomAndSemicolons() throws IOException {
		EntityExchangeResult<byte[]> result = download("csv", ALL_ROUTES_HOURLY);
		byte[] body = result.getResponseBody();

		assertThat(Arrays.copyOf(body, 3)).containsExactly(TableWriters.BOM);
		List<String> lines = new String(body, 3, body.length - 3, StandardCharsets.UTF_8).lines().toList();
		assertThat(lines.getFirst()).isEqualTo("уровень;объект;название;период;прогноз;p10;p90;источник");
		assertThat(lines).hasSize(14_640 + 1);
		assertThat(result.getResponseHeaders().getFirst("X-Rows")).isEqualTo("14640");
		assertThat(predictionsByCell(lines)).isEqualTo(submissionByCell());
	}

	@Test
	void xlsxHoldsTheSameNumbersAsCsv() throws IOException {
		byte[] xlsx = download("xlsx", ALL_ROUTES_HOURLY).getResponseBody();
		byte[] csv = download("csv", ALL_ROUTES_HOURLY).getResponseBody();

		double csvTotal = new String(csv, 3, csv.length - 3, StandardCharsets.UTF_8).lines().skip(1)
			.mapToDouble(l -> Double.parseDouble(l.split(";")[4]))
			.sum();
		try (ReadableWorkbook wb = new ReadableWorkbook(new ByteArrayInputStream(xlsx));
				Stream<Row> rows = wb.getFirstSheet().openStream()) {
			List<Row> all = rows.toList();
			assertThat(all).hasSize(14_640 + 1);
			assertThat(all.getFirst().getCellAsString(0)).contains("уровень");
			double xlsxTotal = all.stream().skip(1).map(r -> r.getCellAsNumber(4).orElseThrow())
				.mapToDouble(BigDecimal::doubleValue)
				.sum();
			assertThat(xlsxTotal).isCloseTo(csvTotal, within(1e-6));
		}
	}

	@Test
	void fileNameIsCyrillicPerRfc6266() {
		HttpHeaders headers = download("csv", "level=route&ids=17&horizon=month&from=2025-12-01").getResponseHeaders();

		String raw = headers.getFirst(HttpHeaders.CONTENT_DISPOSITION);
		assertThat(raw).startsWith("attachment").contains("filename*=UTF-8''");
		assertThat(ContentDisposition.parse(raw).getFilename())
			.isEqualTo("прогноз_посадок_маршрут_17_2025-12-01_2025-12-31.csv");
	}

	@Test
	void everyStopByDayFitsAndNamesWithQuotesStayInOneColumn() {
		byte[] body = download("csv", "level=stop&from=2025-11-01&to=2025-12-31&granularity=day").getResponseBody();
		List<String> lines = new String(body, 3, body.length - 3, StandardCharsets.UTF_8).lines().skip(1).toList();

		int stops = TestArtifacts.model().network().stops().size();
		assertThat(lines).hasSize(stops * 61);
		// названия вида Метро «ВДНХ»: ёлочки для CSV не особые, строка остаётся в своих восьми колонках
		assertThat(lines).filteredOn(l -> l.contains("«")).isNotEmpty()
			.allSatisfy(l -> assertThat(l.replaceAll("\"[^\"]*(\"\"[^\"]*)*\"", "X").split(";")).hasSize(8));
	}

	@Test
	void segmentExportsOneRowPerHourUnderItsOwnName() {
		List<RouteStop> stops = TestArtifacts.model().network().routeStops(17).stream()
			.filter(s -> s.direction() == 0)
			.sorted(Comparator.comparingInt(RouteStop::seq))
			.toList();
		String from = stops.getFirst().stopId();
		String to = stops.get(3).stopId();
		EntityExchangeResult<byte[]> result = download("csv", "level=segment&ids=17&direction=0&fromStop=" + from
				+ "&toStop=" + to + "&horizon=day&from=2025-11-03");

		byte[] body = result.getResponseBody();
		List<String> lines = new String(body, 3, body.length - 3, StandardCharsets.UTF_8).lines().skip(1).toList();
		assertThat(lines).hasSize(24)
			.allSatisfy(l -> assertThat(l).startsWith("segment;17:0:" + from + "-" + to + ";"));
		assertThat(ContentDisposition.parse(result.getResponseHeaders().getFirst(HttpHeaders.CONTENT_DISPOSITION))
			.getFilename()).isEqualTo("прогноз_посадок_участок_17_" + from + "-" + to + "_2025-11-03_2025-11-03.csv");
	}

	@Test
	void unknownFormatIsAProblemDetail() {
		client.get().uri("/api/v1/export?format=pdf&level=route").exchange()
			.expectStatus().isBadRequest()
			.expectBody().jsonPath("$.errors[0].field").isEqualTo("format");
	}

	private EntityExchangeResult<byte[]> download(String format, String query) {
		return client.get().uri("/api/v1/export?format=" + format + "&" + query).exchange()
			.expectStatus().isOk()
			.expectBody(byte[].class).returnResult();
	}

	/** «route;date;hour» -> прогноз из выгрузки, период вида 2025-11-01T08:00. */
	private static List<String> predictionsByCell(List<String> lines) {
		return lines.stream().skip(1).map(l -> l.split(";")).map(f -> {
			String[] ts = f[3].split("T");
			return f[1] + ";" + ts[0] + ";" + Integer.parseInt(ts[1].substring(0, 2)) + ";" + f[4];
		}).sorted().toList();
	}

	private static List<String> submissionByCell() throws IOException {
		return Files.readAllLines(TestArtifacts.repoRoot().resolve(TestArtifacts.model().info().defaultSubmission()))
			.stream().skip(1).sorted().toList();
	}

}
