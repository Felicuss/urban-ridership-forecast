package ru.mojarung.tramload.api.dto;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

/** Паспорт модели: версия, горизонт, качество и область применимости. */
public record MetaResponse(String modelVersion, String gitCommit, String generatedAt, LocalDate forecastOrigin,
		LocalDate horizonFrom, LocalDate horizonTo, LocalDate timelineFrom, LocalDate timelineTo, List<Integer> routes,
		String timezone, double leaderboardWapeScore,
		String defaultSubmission, Map<String, Object> quality, List<String> applicability) {
}
