package ru.mojarung.tramload.application;

import java.time.DateTimeException;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.regex.Pattern;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;
import ru.mojarung.tramload.domain.agent.ChatMessage;
import ru.mojarung.tramload.domain.agent.ToolCall;

/** Период диалога отделён от экрана. Команда показа не может подменить явно выбранный период. */
final class AgentTurn {
	static final String STATE = "agent-context-v1:";
	private static final JsonMapper JSON = JsonMapper.builder().build();
	private static final Pattern ISO = Pattern.compile("\\b(20\\d{2}-\\d{2}-\\d{2})\\b");
	private static final String MONTH_NAME = "январ[ьяе]|феврал[ьяе]|марта?|апрел[ьяе]|ма[йяе]|июн[ьяе]|июл[ьяе]|август[ае]?|сентябр[ьяе]|окт(?:ябр[ьяе]|ряб[ьяе])|ноябр[ьяе]|декабр[ьяе]";
	private static final Pattern DAY = Pattern.compile("(?iu)(?<!\\d)([0-3]?\\d)\\s+(" + MONTH_NAME + ")(?:\\s+(20\\d{2}))?");
	private static final Pattern MONTH = Pattern.compile("(?iu)(?<![а-яё])(" + MONTH_NAME + ")(?![а-яё])(?:\\s+(20\\d{2}))?");
	private static final Pattern YEAR = Pattern.compile("\\b(20\\d{2})\\b");
	private static final List<String> MONTHS = List.of("янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек");
	final Map<String, Object> focus = new HashMap<>();
	private final Map<String, Object> screen;
	final boolean show;
	final boolean network;
	final boolean singleDay;
	private final boolean lockPeriod;
	private boolean shown;

	AgentTurn(String message, Map<String, Object> screen, List<ChatMessage> history) {
		this.screen = screen == null ? Map.of() : new HashMap<>(screen);
		focus.putAll(this.screen);
		String text = message.toLowerCase(Locale.ROOT);
		boolean inherited = false;
		for (int i = history.size() - 1; i >= 0; i--) {
			ChatMessage m = history.get(i);
			if (!isState(m)) continue;
			var state = JSON.readTree(m.content().substring(STATE.length()));
			// Ручная смена даты/маршрута важнее старого диалога; «ту же дату» явно ссылается на диалог.
			boolean sameScreen = List.of("date", "route", "stop").stream().allMatch(k ->
					Objects.equals(state.path("screen").path(k).asString(null), Objects.toString(this.screen.get(k), null)));
			if (sameScreen || text.matches("(?s).*(эту же|ту же|этот день|этой дат|этом маршрут).*")) {
				inherited = true;
				state.path("focus").properties().forEach(e -> focus.put(e.getKey(), JSON.convertValue(e.getValue(), Object.class)));
			}
			break;
		}
		show = text.matches("(?s).*(покажи|покажешь|открой|выведи|показать.*карт).*")
				&& !text.matches("(?s).*не\\s+(показы|открыва).*");
		network = text.contains("всей сети") || text.contains("всю сеть") || text.contains("график сети");
		String reference = Objects.toString(focus.get("date"), "2025-11-01");
		try { LocalDate.parse(reference); }
		catch (DateTimeException e) { reference = "2025-11-01"; focus.remove("date"); }
		var year = YEAR.matcher(text);
		int y = year.find() ? Integer.parseInt(year.group(1)) : LocalDate.parse(reference).getYear();
		var day = DAY.matcher(text);
		var iso = ISO.matcher(text);
		boolean explicitDay = false;
		boolean namedMonth = false;
		var monthName = MONTH.matcher(text);
		try {
			if (iso.find()) {
				focus.put("date", LocalDate.parse(iso.group(1)).toString());
				explicitDay = true;
			} else if (day.find()) {
				String month = day.group(2).substring(0, 3).replace("мая", "май").replace("мае", "май");
				focus.put("date", LocalDate.of(day.group(3) == null ? y : Integer.parseInt(day.group(3)),
						MONTHS.indexOf(month) + 1, Integer.parseInt(day.group(1))).toString());
				explicitDay = true;
			} else if (monthName.find()) {
				String month = monthName.group(1).substring(0, 3).replace("мая", "май").replace("мае", "май");
				focus.put("date", LocalDate.of(monthName.group(2) == null ? y : Integer.parseInt(monthName.group(2)),
						MONTHS.indexOf(month) + 1, 1).toString());
				namedMonth = true;
			}
		} catch (DateTimeException ignored) {
			// Неверную дату уточнит модель; не преобразуем 31 февраля в другую дату.
		}
		if (!explicitDay && (text.contains("завтра") || text.contains("вчера"))) {
			focus.put("date", LocalDate.parse(reference).plusDays(text.contains("завтра") ? 1 : -1).toString());
			explicitDay = true;
		}
		boolean week = text.contains("недел");
		boolean month = namedMonth || text.contains("месяц") && !text.contains("по месяцам");
		boolean wholeYear = text.matches("(?s).*(весь|целый|за|на)\\s+20\\d{2}\\s*год.*") || text.contains("годовой график");
		if (wholeYear) {
			focus.put("date", y + "-01-01");
			focus.put("horizon", "year");
		} else if (week) focus.put("horizon", "week");
		else if (month) focus.put("horizon", "month");
		else if (explicitDay || text.contains("этот день") || text.contains("же дату")) focus.put("horizon", "day");
		lockPeriod = explicitDay || namedMonth || wholeYear || inherited;
		singleDay = !week && !month && !wholeYear && (explicitDay || "day".equals(focus.get("horizon")));
	}

	static boolean isState(ChatMessage m) {
		return m.role() == ChatMessage.Role.SYSTEM && m.content() != null && m.content().startsWith(STATE);
	}

	ChatMessage state() {
		return ChatMessage.system(STATE + JSON.writeValueAsString(Map.of("focus", focus, "screen", screen)));
	}

	ToolCall prepare(ToolCall call) {
		if (!"ui_show".equals(call.name())) return call;
		tools.jackson.databind.JsonNode parsed;
		try { parsed = JSON.readTree(call.arguments()); }
		catch (JacksonException e) { return call; }
		if (!(parsed instanceof ObjectNode args)) return call;
		for (String k : List.of("date", "horizon")) {
			if (lockPeriod && focus.get(k) != null) args.put(k, focus.get(k).toString());
		}
		if (network) {
			args.put("network", true);
			args.remove("route");
			args.remove("stop_id");
		}
		return new ToolCall(call.id(), call.name(), JSON.writeValueAsString(args));
	}

	void applied(Map<String, Object> action) {
		shown = true;
		for (String k : List.of("date", "hour", "route", "stop", "view", "horizon", "tab")) {
			if (action.get(k) != null) focus.put(k, action.get(k));
		}
		if (Boolean.TRUE.equals(action.get("network"))) {
			focus.remove("route");
			focus.remove("stop");
		}
	}

	boolean missingShow() { return show && !shown; }
}
