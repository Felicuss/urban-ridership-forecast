package ru.mojarung.tramload.domain;

import java.util.Arrays;
import java.util.List;

/**
 * Компоненты прогноза по всем ячейкам сетки в примитивных массивах. Массивы наружу не отдаются,
 * поэтому объект неизменяемый и безопасно читается из любого числа потоков.
 */
public final class ForecastComponents {

	private final ForecastGrid grid;
	private final byte[] dayOfWeek;
	private final DayKind[] kind;
	private final boolean[] holiday;
	private final boolean[] workingSaturday;
	private final boolean[] preNewYear;
	private final boolean[] newYearEve;
	private final boolean[] restorable;
	private final double[] base;
	private final double[] baseRestored;
	private final double[] route5Shape;
	private final double[] precipDay;
	private final double[] precipHour;
	private final double[] tempDay;
	private final double[] calib;
	private final double[] prediction;

	private ForecastComponents(ForecastGrid grid, List<CellComponents> cells) {
		this.grid = grid;
		int n = grid.size();
		dayOfWeek = new byte[n];
		kind = new DayKind[n];
		holiday = new boolean[n];
		workingSaturday = new boolean[n];
		preNewYear = new boolean[n];
		newYearEve = new boolean[n];
		restorable = new boolean[n];
		base = new double[n];
		baseRestored = new double[n];
		route5Shape = new double[n];
		precipDay = new double[n];
		precipHour = new double[n];
		tempDay = new double[n];
		calib = new double[n];
		prediction = new double[n];
		boolean[] seen = new boolean[n];
		for (CellComponents c : cells) {
			int cell = grid.cell(grid.routeIndex(c.route()), grid.dayIndex(c.date()), c.hour());
			if (seen[cell]) {
				throw new IllegalArgumentException("ячейка повторяется: " + c.route() + " " + c.date() + " " + c.hour());
			}
			seen[cell] = true;
			fill(cell, c);
		}
		if (cells.size() != n) {
			throw new IllegalArgumentException("в компонентах " + cells.size() + " ячеек, в сетке " + n);
		}
	}

	public static ForecastComponents of(ForecastGrid grid, List<CellComponents> cells) {
		return new ForecastComponents(grid, cells);
	}

	private void fill(int cell, CellComponents c) {
		dayOfWeek[cell] = (byte) c.dayOfWeek();
		kind[cell] = c.kind();
		holiday[cell] = c.holiday();
		workingSaturday[cell] = c.workingSaturday();
		preNewYear[cell] = c.preNewYear();
		newYearEve[cell] = c.newYearEve();
		restorable[cell] = c.restorable();
		base[cell] = c.base();
		baseRestored[cell] = c.baseRestored();
		route5Shape[cell] = c.route5Shape();
		precipDay[cell] = c.precipDay();
		precipHour[cell] = c.precipHour();
		tempDay[cell] = c.tempDay();
		calib[cell] = c.calib();
		prediction[cell] = c.prediction();
	}

	public ForecastGrid grid() {
		return grid;
	}

	public int dayOfWeek(int cell) {
		return dayOfWeek[cell];
	}

	public DayKind kind(int cell) {
		return kind[cell];
	}

	/** Тип дня по индексу дня: он одинаков у всех маршрутов. */
	public DayKind dayKind(int dayIndex) {
		return kind[grid.cell(0, dayIndex, 0)];
	}

	public boolean holiday(int cell) {
		return holiday[cell];
	}

	public boolean workingSaturday(int cell) {
		return workingSaturday[cell];
	}

	public boolean preNewYear(int cell) {
		return preNewYear[cell];
	}

	public boolean newYearEve(int cell) {
		return newYearEve[cell];
	}

	public boolean restorable(int cell) {
		return restorable[cell];
	}

	public double base(int cell) {
		return base[cell];
	}

	public double baseRestored(int cell) {
		return baseRestored[cell];
	}

	public double route5Shape(int cell) {
		return route5Shape[cell];
	}

	public double precipDay(int cell) {
		return precipDay[cell];
	}

	public double precipHour(int cell) {
		return precipHour[cell];
	}

	/** Множитель до лучшего конкурсного прогноза (v6) в ячейке: при коэффициентах по умолчанию формула даёт v6. */
	public double calib(int cell) {
		return calib[cell];
	}

	public double tempDay(int cell) {
		return tempDay[cell];
	}

	/** Прогноз по умолчанию, как его посчитал экспорт на Python. Копия: исходный массив не меняется. */
	public double[] exportedPrediction() {
		return Arrays.copyOf(prediction, prediction.length);
	}

}
