package ru.mojarung.tramload.domain.coefficient;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import ru.mojarung.tramload.domain.Coefficients;
import ru.mojarung.tramload.domain.ValidationException;
import ru.mojarung.tramload.domain.ValidationException.Violation;

/**
 * Каталог ползунков: значения по умолчанию, диапазоны и перевод переопределений из запроса в {@link Coefficients}.
 * Всё, что вне диапазона или неизвестно, отклоняется целиком со списком нарушений.
 */
public final class CoefficientCatalog {

	public static final Set<String> REQUIRED_KEYS = Set.of("level_nov", "level_dec", "traffic_weight",
			"holiday_to_sunday", "working_saturday", "last_workdays_dec", "dec31_day", "dec31_free_from_hour",
			"weekend_restore_date", "t1_start", "t1_route7", "route5_on", "route5_start", "route5_workday", "weather",
			"precip_day_coef", "hour_precip_coef", "frost_coef");

	private final List<CoefficientSpec> ordered;
	private final Map<String, CoefficientSpec> specs;
	private final Coefficients defaults;

	public CoefficientCatalog(List<CoefficientSpec> specs) {
		Map<String, CoefficientSpec> byKey = new LinkedHashMap<>();
		specs.forEach(s -> byKey.put(s.key(), s));
		if (!byKey.keySet().containsAll(REQUIRED_KEYS)) {
			List<String> missing = REQUIRED_KEYS.stream().filter(k -> !byKey.containsKey(k)).sorted().toList();
			throw new IllegalArgumentException("в каталоге ползунков нет ключей " + missing);
		}
		this.ordered = List.copyOf(specs);
		this.specs = Map.copyOf(byKey);
		Map<String, Object> values = new LinkedHashMap<>();
		byKey.values().forEach(s -> values.put(s.key(), s.defaultValue()));
		this.defaults = build(values);
	}

	/** Ползунки в порядке каталога: по группам, как их показывать в интерфейсе. */
	public List<CoefficientSpec> specs() {
		return ordered;
	}

	public Coefficients defaults() {
		return defaults;
	}

	/** Значения по умолчанию с переопределениями из запроса. Пустые переопределения дают значения по умолчанию. */
	public Coefficients resolve(Map<String, ?> overrides) {
		if (overrides == null || overrides.isEmpty()) {
			return defaults;
		}
		Map<String, Object> values = new LinkedHashMap<>();
		specs.values().forEach(s -> values.put(s.key(), s.defaultValue()));
		List<Violation> violations = new ArrayList<>();
		overrides.forEach((key, raw) -> {
			CoefficientSpec spec = specs.get(key);
			if (spec == null) {
				violations.add(new Violation("coefficients." + key, "неизвестный коэффициент"));
				return;
			}
			try {
				Object value = spec.type().coerce(raw);
				checkRange(spec, value);
				values.put(key, value);
			}
			catch (IllegalArgumentException ex) {
				violations.add(new Violation("coefficients." + key, ex.getMessage()));
			}
		});
		if (!violations.isEmpty()) {
			throw new ValidationException(violations);
		}
		return build(values);
	}

	@SuppressWarnings({ "unchecked", "rawtypes" })
	private static void checkRange(CoefficientSpec spec, Object value) {
		if (spec.min() == null || spec.max() == null || value instanceof Boolean) {
			return;
		}
		Comparable v = comparable(value);
		if (v.compareTo(comparable(spec.min())) < 0 || v.compareTo(comparable(spec.max())) > 0) {
			throw new IllegalArgumentException("вне диапазона " + spec.min() + " - " + spec.max());
		}
	}

	private static Comparable<?> comparable(Object value) {
		return switch (value) {
			case Number n -> n.doubleValue();
			case Comparable<?> c -> c;
			default -> throw new IllegalArgumentException("значение нельзя сравнить: " + value);
		};
	}

	private static Coefficients build(Map<String, Object> v) {
		return new Coefficients(
				num(v, "level_nov"), num(v, "level_dec"), num(v, "traffic_weight"),
				num(v, "holiday_to_sunday"), num(v, "working_saturday"), num(v, "last_workdays_dec"),
				num(v, "dec31_day"), ((Number) v.get("dec31_free_from_hour")).intValue(),
				(LocalDate) v.get("weekend_restore_date"), (LocalDate) v.get("t1_start"), num(v, "t1_route7"),
				(Boolean) v.get("route5_on"), (LocalDateTime) v.get("route5_start"), num(v, "route5_workday"),
				(Boolean) v.get("weather"), num(v, "precip_day_coef"), num(v, "hour_precip_coef"), num(v, "frost_coef"));
	}

	/** Значения ползунков сценария по ключам каталога: фронт сверяет по ним положение ползунков. */
	public static Map<String, Object> values(Coefficients c) {
		Map<String, Object> out = new LinkedHashMap<>();
		out.put("level_nov", c.levelNov());
		out.put("level_dec", c.levelDec());
		out.put("traffic_weight", c.trafficWeight());
		out.put("holiday_to_sunday", c.holidayToSunday());
		out.put("working_saturday", c.workingSaturday());
		out.put("last_workdays_dec", c.lastWorkdaysDec());
		out.put("dec31_day", c.dec31Day());
		out.put("dec31_free_from_hour", c.dec31FreeFromHour());
		out.put("weekend_restore_date", c.weekendRestoreDate().toString());
		out.put("t1_start", c.t1Start().toString());
		out.put("t1_route7", c.t1Route7());
		out.put("route5_on", c.route5On());
		out.put("route5_start", c.route5Start().toString());
		out.put("route5_workday", c.route5Workday());
		out.put("weather", c.weather());
		out.put("precip_day_coef", c.precipDayCoef());
		out.put("hour_precip_coef", c.hourPrecipCoef());
		out.put("frost_coef", c.frostCoef());
		return out;
	}

	private static double num(Map<String, Object> v, String key) {
		return ((Number) v.get(key)).doubleValue();
	}

}
