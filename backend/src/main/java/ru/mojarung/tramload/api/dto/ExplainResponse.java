package ru.mojarung.tramload.api.dto;

import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;

/** Посадки за сутки после каждого шага формулы и вклад шага. */
@Schema(description = "Шаги: profile - профиль последних недель, level - уровень месяца, calendar - календарь, "
		+ "network - события сети, weather - погода, model - поправка до v25, scenario - события сценария")
public record ExplainResponse(Integer route, String date, List<Step> steps) {

	public record Step(String key, double value, double delta) {
	}

}
