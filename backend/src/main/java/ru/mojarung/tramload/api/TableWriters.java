package ru.mojarung.tramload.api;

import java.io.BufferedWriter;
import java.io.IOException;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.io.UncheckedIOException;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;

import org.dhatim.fastexcel.Workbook;
import org.dhatim.fastexcel.Worksheet;

import ru.mojarung.tramload.application.ExportService;
import ru.mojarung.tramload.application.ExportService.ExportRow;
import ru.mojarung.tramload.application.ExportService.ExportTable;

/**
 * Запись таблицы выгрузки в поток. CSV - UTF-8 с BOM, разделитель «;», точка в дробях, как в сабмите:
 * Excel с русской локалью открывает его без мастера импорта. XLSX пишется FastExcel построчно.
 */
final class TableWriters {

	static final byte[] BOM = { (byte) 0xEF, (byte) 0xBB, (byte) 0xBF };
	private static final char SEPARATOR = ';';
	private static final int XLSX_FLUSH_ROWS = 10_000;

	private TableWriters() {
	}

	static void csv(ExportTable table, OutputStream out) {
		try {
			out.write(BOM);
			Writer w = new BufferedWriter(new OutputStreamWriter(out, StandardCharsets.UTF_8), 1 << 16);
			w.write(String.join(String.valueOf(SEPARATOR), ExportService.HEADER));
			w.write("\r\n");
			for (Iterator<ExportRow> it = table.rows().iterator(); it.hasNext();) {
				ExportRow r = it.next();
				w.write(r.level() + SEPARATOR + r.id() + SEPARATOR + quote(r.name()) + SEPARATOR + r.period() + SEPARATOR
						+ number(r.p50(), r.decimals()) + SEPARATOR + number(r.p10(), r.decimals()) + SEPARATOR
						+ number(r.p90(), r.decimals()) + "\r\n");
			}
			w.flush();
		}
		catch (IOException ex) {
			throw new UncheckedIOException(ex);
		}
	}

	static void xlsx(ExportTable table, OutputStream out) {
		try (Workbook wb = new Workbook(out, "tram-load-api", "1.0")) {
			Worksheet ws = wb.newWorksheet("Прогноз");
			for (int c = 0; c < ExportService.HEADER.size(); c++) {
				ws.value(0, c, ExportService.HEADER.get(c));
			}
			ws.style(0, 0).bold().set();
			int row = 1;
			for (Iterator<ExportRow> it = table.rows().iterator(); it.hasNext(); row++) {
				ExportRow r = it.next();
				ws.value(row, 0, r.level());
				ws.value(row, 1, r.id());
				ws.value(row, 2, r.name());
				ws.value(row, 3, r.period());
				ws.value(row, 4, r.p50());
				ws.value(row, 5, r.p10());
				ws.value(row, 6, r.p90());
				if (row % XLSX_FLUSH_ROWS == 0) {
					ws.flush();
				}
			}
			ws.finish();
		}
		catch (IOException ex) {
			throw new UncheckedIOException(ex);
		}
	}

	/** Целые без «.0», чтобы выгрузка маршрутов по часам совпадала с форматом сабмита. */
	static String number(double value, int decimals) {
		return decimals == 0 ? Long.toString((long) value) : Double.toString(value);
	}

	/** Поле с разделителем или кавычкой берём в кавычки по RFC 4180. */
	static String quote(String value) {
		if (value.indexOf(SEPARATOR) < 0 && value.indexOf('"') < 0 && value.indexOf('\n') < 0) {
			return value;
		}
		return '"' + value.replace("\"", "\"\"") + '"';
	}

}
