package ru.mojarung.tramload.domain;

import java.time.LocalDate;
import java.util.Map;

/**
 * Паспорт модели для /meta: версия, коммит, дата прогноза, качество на лидерборде и бэктесте.
 * metrics - содержимое backtest_metrics.json как есть, его структура описана в analysis/export_horizons.py.
 */
public record ModelInfo(
		String modelVersion,
		String gitCommit,
		String generatedAt,
		LocalDate forecastOrigin,
		double leaderboardWapeScore,
		String defaultSubmission,
		Map<String, Object> metrics) {

	public ModelInfo {
		metrics = Map.copyOf(metrics);
	}

}
