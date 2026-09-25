package ru.mojarung.tramload.api.dto;

import java.util.List;
import java.util.Map;

import io.swagger.v3.oas.annotations.media.Schema;

/** Кадры тепловой карты по сценарию. */
public record NetworkLoadRequest(
		@Schema(example = "2025-11-03") String date,
		@Schema(example = "6-23") String hours,
		Map<String, Object> coefficients,
		List<EventDto> events) {
}
