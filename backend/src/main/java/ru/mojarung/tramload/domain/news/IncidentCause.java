package ru.mojarung.tramload.domain.news;

import java.util.Arrays;

/** Причина сбоя в сообщении Дептранса. Коды совпадают с разметкой analysis/s45_incident_adjustment.py. */
public enum IncidentCause {

	CONTACT_NETWORK("contact_network", "неисправность контактной сети"),
	ROAD_ACCIDENT("road_accident", "ДТП"),
	BLOCKED_TRACKS("blocked_tracks", "автомобиль на путях"),
	TECHNICAL("technical_or_unspecified", "технические причины");

	private final String code;
	private final String label;

	IncidentCause(String code, String label) {
		this.code = code;
		this.label = label;
	}

	public String code() {
		return code;
	}

	public String label() {
		return label;
	}

	public static IncidentCause of(String code) {
		return Arrays.stream(values()).filter(c -> c.code.equals(code)).findFirst().orElse(TECHNICAL);
	}

	/** Причина по тексту сообщения: те же признаки, что в разметке 2025 года. */
	public static IncidentCause classify(String text) {
		if (text.contains("ДТП")) {
			return ROAD_ACCIDENT;
		}
		if (text.contains("контактн")) {
			return CONTACT_NETWORK;
		}
		return text.contains("автомобил") ? BLOCKED_TRACKS : TECHNICAL;
	}

}
