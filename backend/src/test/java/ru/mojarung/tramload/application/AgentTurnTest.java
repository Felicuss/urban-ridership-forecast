package ru.mojarung.tramload.application;

import static org.assertj.core.api.Assertions.assertThat;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import ru.mojarung.tramload.domain.agent.ToolCall;

class AgentTurnTest {
	private static final Map<String, Object> SCREEN = Map.of("date", "2025-11-16", "horizon", "month", "route", 17);

	@Test
	void newNamedMonthOverridesPreviousDialogueDate() {
		AgentTurn old = new AgentTurn("нагрузка 4 октября 2027", SCREEN, List.of());
		AgentTurn next = new AgentTurn("покажи ноябрь 2025", SCREEN, List.of(old.state()));
		assertThat(next.focus).containsEntry("date", "2025-11-01").containsEntry("horizon", "month");
	}

	@Test
	void explicitDayAndFollowupOverrideStaleScreen() {
		AgentTurn first = new AgentTurn("нагрузка за 4 октября 2027 года", SCREEN, List.of());
		assertThat(first.focus).containsEntry("date", "2027-10-04").containsEntry("horizon", "day");
		AgentTurn next = new AgentTurn("покажешь маршрут на эту же дату", SCREEN, List.of(first.state()));
		assertThat(next.focus).containsEntry("date", "2027-10-04").containsEntry("horizon", "day");
		assertThat(next.prepare(new ToolCall("a", "ui_show", "{\"date\":\"2025-11-16\",\"horizon\":\"month\"}")).arguments())
			.contains("2027-10-04", "day").doesNotContain("2025-11-16", "month");
	}

	@Test
	void typoKeepsDialogueYearAndDayHorizon() {
		AgentTurn first = new AgentTurn("за 4 октября 2027 года", SCREEN, List.of());
		AgentTurn next = new AgentTurn("покажи маршрут за 8 октрябя?", SCREEN, List.of(first.state()));
		assertThat(next.focus).containsEntry("date", "2027-10-08").containsEntry("horizon", "day");
	}

	@Test
	void manualDateChangeWinsForNewQuestion() {
		AgentTurn first = new AgentTurn("за 4 октября 2027", SCREEN, List.of());
		AgentTurn next = new AgentTurn("нагрузка сегодня на экране", Map.of("date", "2026-05-05"), List.of(first.state()));
		assertThat(next.focus).containsEntry("date", "2026-05-05");
	}

	@Test
	void yearSelectionClearsRouteAndDoesNotBecomeDay() {
		AgentTurn turn = new AgentTurn("Покажи график всей сети за весь 2027 год по месяцам", SCREEN, List.of());
		assertThat(turn.focus).containsEntry("date", "2027-01-01").containsEntry("horizon", "year");
		assertThat(turn.singleDay).isFalse();
		assertThat(turn.prepare(new ToolCall("a", "ui_show", "{\"route\":17}")).arguments())
			.contains("\"network\":true").doesNotContain("route");
	}

	@Test
	void routeNumberIsNotADateAndWeekRemainsWeek() {
		AgentTurn ordinaryWords = new AgentTurn("самая загруженная остановка", SCREEN, List.of());
		assertThat(ordinaryWords.focus).containsEntry("date", "2025-11-16");
		AgentTurn route = new AgentTurn("на 17 маршруте", SCREEN, List.of());
		assertThat(route.focus).containsEntry("date", "2025-11-16");
		AgentTurn week = new AgentTurn("нагрузка за неделю 4 октября 2027", SCREEN, List.of());
		assertThat(week.focus).containsEntry("horizon", "week");
		assertThat(week.singleDay).isFalse();
	}
}
