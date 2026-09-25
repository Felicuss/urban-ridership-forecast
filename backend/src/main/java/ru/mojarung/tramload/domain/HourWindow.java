package ru.mojarung.tramload.domain;

/** Часы суток с first по last включительно, например утренний пик 7-9. */
public record HourWindow(int first, int last) {

	public static final HourWindow ALL_DAY = new HourWindow(0, ForecastGrid.HOURS - 1);

	public HourWindow {
		if (first < 0 || last >= ForecastGrid.HOURS || first > last) {
			throw new IllegalArgumentException("часы должны быть в 0-23 и идти по возрастанию: " + first + "-" + last);
		}
	}

	public boolean contains(int hour) {
		return hour >= first && hour <= last;
	}

	@Override
	public String toString() {
		return first + "-" + last;
	}

}
