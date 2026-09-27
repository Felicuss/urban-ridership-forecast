package ru.mojarung.tramload.domain;

import java.time.LocalDate;
import java.util.List;

/**
 * Пересчёт прогноза по сценарию. Порядок операций повторяет analysis/s10_forecast.py (apply_rules)
 * и analysis/export_components.py (recompute): правила, погода, множитель ячейки до лучшего конкурсного
 * прогноза (v25), события сценария. От порядка зависит совпадение с сабмитом до последнего знака.
 * Эталонные тесты сверяют результат с сабмитом и с Python на пяти наборах коэффициентов.
 */
public final class ForecastEngine {

	private static final int ROUTE_T1 = 7;
	private static final int ROUTE_NEW = 5;
	private static final int NOVEMBER = 11;
	private static final double FROST_THRESHOLD = -10.0;
	private static final double HOUR_PRECIP_CAP = 3.0;
	private static final int FRIDAY = 4;

	private final ForecastComponents components;
	private final ModelConstants constants;

	public ForecastEngine(ForecastComponents components, ModelConstants constants) {
		this.components = components;
		this.constants = constants;
	}

	public double[] compute(Scenario scenario) {
		ForecastGrid grid = components.grid();
		double[] out = new double[grid.size()];
		Coefficients c = scenario.coefficients();
		for (int r = 0; r < grid.routes().size(); r++) {
			int route = grid.routes().get(r);
			for (int d = 0; d < grid.days(); d++) {
				LocalDate date = grid.date(d);
				for (int h = 0; h < ForecastGrid.HOURS; h++) {
					int cell = grid.cell(r, d, h);
					double rules = route == ROUTE_NEW ? route5(cell, date, h, c) : regular(cell, route, date, h, c);
					double value = weather(cell, rules, c) * components.calib(cell);
					out[cell] = Math.max(events(value, route, date, h, scenario.events()), 0.0);
				}
			}
		}
		return out;
	}

	/**
	 * Шаги формулы для водопада «из чего сложился прогноз»: посадки за сутки после каждого шага, по одному
	 * маршруту или по всей сети (route = null). Порядок шагов - {@link Explanation#STEPS}, последний шаг
	 * равен прогнозу сценария.
	 */
	public Explanation explain(Scenario scenario, Integer route, LocalDate date) {
		ForecastGrid grid = components.grid();
		int d = grid.dayIndex(date);
		Coefficients c = scenario.coefficients();
		double[] totals = new double[Explanation.STEPS.size()];
		for (int r = 0; r < grid.routes().size(); r++) {
			int id = grid.routes().get(r);
			if (route != null && route != id) {
				continue;
			}
			for (int h = 0; h < ForecastGrid.HOURS; h++) {
				int cell = grid.cell(r, d, h);
				double base = id == ROUTE_NEW ? 0.0 : components.base(cell);
				double levelled = base * level(date.getMonthValue(), c);
				double calendar = id == ROUTE_NEW ? 0.0 : calendar(cell, levelled, h, c);
				double rules = id == ROUTE_NEW ? route5(cell, date, h, c) : regular(cell, id, date, h, c);
				double weathered = weather(cell, rules, c);
				double model = weathered * components.calib(cell);
				double[] step = { base, levelled, calendar, rules, weathered, model,
						Math.max(events(model, id, date, h, scenario.events()), 0.0) };
				for (int i = 0; i < totals.length; i++) {
					totals[i] += step[i];
				}
			}
		}
		return new Explanation(totals);
	}

	/** Календарь без событий сети: праздник, рабочая суббота, предновогодние дни, 31 декабря. */
	private double calendar(int cell, double levelled, int hour, Coefficients c) {
		ForecastComponents k = components;
		double pred = levelled * (k.holiday(cell) && k.dayOfWeek(cell) <= FRIDAY ? c.holidayToSunday() : 1.0);
		pred = pred * (k.workingSaturday(cell) ? c.workingSaturday() : 1.0);
		pred = pred * (k.preNewYear(cell) ? c.lastWorkdaysDec() : 1.0);
		pred = pred * (k.newYearEve(cell) ? c.dec31Day() : 1.0);
		return freeTravel(cell, hour, c) ? 0.0 : pred;
	}

	/** Посадки за сутки после каждого шага формулы. */
	public record Explanation(double[] totals) {

		/** profile - профиль последних недель, level - уровень месяца, calendar - календарь, network - события
		 * сети (выходные 7 и 50, Т1, маршрут 5), weather - погода, model - поправка до v25, scenario - события сценария. */
		public static final List<String> STEPS = List.of("profile", "level", "calendar", "network", "weather", "model",
				"scenario");

	}

	/** Уровень месяца: сезонный из ползунка, при весе трафика - среднее в логарифме с уровнем по трафику. */
	double level(int month, Coefficients c) {
		double seasonal = month == NOVEMBER ? c.levelNov() : c.levelDec();
		double traffic = month == NOVEMBER ? constants.trafficLevelNov() : constants.trafficLevelDec();
		double w = c.trafficWeight();
		if (w == 0.0) {
			return seasonal;
		}
		return Math.exp((1 - w) * Math.log(seasonal) + w * Math.log(traffic));
	}

	private double regular(int cell, int route, LocalDate date, int hour, Coefficients c) {
		ForecastComponents k = components;
		double level = level(date.getMonthValue(), c);
		double pred;
		if (k.restorable(cell) && !date.isBefore(c.weekendRestoreDate())) {
			pred = k.baseRestored(cell) * (level * (k.holiday(cell) ? c.holidayToSunday() : 1.0));
		}
		else {
			pred = k.base(cell) * level;
			pred = pred * (k.holiday(cell) && k.dayOfWeek(cell) <= FRIDAY ? c.holidayToSunday() : 1.0);
			pred = pred * (k.workingSaturday(cell) ? c.workingSaturday() : 1.0);
			pred = pred * (k.preNewYear(cell) ? c.lastWorkdaysDec() : 1.0);
		}
		pred = pred * (k.newYearEve(cell) ? c.dec31Day() : 1.0);
		if (freeTravel(cell, hour, c)) {
			pred = 0.0;
		}
		boolean t1 = route == ROUTE_T1 && !date.isBefore(c.t1Start());
		return pred * (t1 ? c.t1Route7() : 1.0);
	}

	private double route5(int cell, LocalDate date, int hour, Coefficients c) {
		boolean launched = c.route5On() && !date.atTime(hour, 0).isBefore(c.route5Start());
		if (!launched || freeTravel(cell, hour, c)) {
			return 0.0;
		}
		double ratio = switch (components.kind(cell)) {
			case SATURDAY -> constants.route5SaturdayRatio();
			case SUNDAY -> constants.route5SundayRatio();
			case WORKDAY -> 1.0;
		};
		return c.route5Workday() * components.route5Shape(cell) * ratio;
	}

	private boolean freeTravel(int cell, int hour, Coefficients c) {
		return components.newYearEve(cell) && hour >= c.dec31FreeFromHour();
	}

	private double weather(int cell, double value, Coefficients c) {
		if (!c.weather()) {
			return value;
		}
		double adj = c.precipDayCoef() * components.precipDay(cell)
				+ c.hourPrecipCoef() * Math.clamp(components.precipHour(cell), 0.0, HOUR_PRECIP_CAP)
				+ c.frostCoef() * Math.max(FROST_THRESHOLD - components.tempDay(cell), 0.0);
		return value * Math.exp(adj);
	}

	private static double events(double value, int route, LocalDate date, int hour, List<ScenarioEvent> events) {
		double out = value;
		for (ScenarioEvent e : events) {
			if (e.covers(route, date, hour)) {
				out = out * e.multiplier();
			}
		}
		return out;
	}

}
