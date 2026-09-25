package ru.mojarung.tramload.domain;

/** Постоянные модели, которые не выносятся на ползунки: уровень по трафику и выходные маршрута 5. */
public record ModelConstants(
		double trafficLevelNov,
		double trafficLevelDec,
		double route5SaturdayRatio,
		double route5SundayRatio) {
}
