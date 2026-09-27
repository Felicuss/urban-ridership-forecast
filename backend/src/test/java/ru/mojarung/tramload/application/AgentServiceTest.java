package ru.mojarung.tramload.application;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.junit.jupiter.api.Test;

import ru.mojarung.tramload.domain.agent.AgentEvent;
import ru.mojarung.tramload.domain.agent.AgentMemory;
import ru.mojarung.tramload.domain.agent.AgentTools;
import ru.mojarung.tramload.domain.agent.ChatMessage;
import ru.mojarung.tramload.domain.agent.LanguageModel;
import ru.mojarung.tramload.domain.agent.ModelReply;
import ru.mojarung.tramload.domain.agent.ToolCall;
import ru.mojarung.tramload.domain.agent.ToolResult;
import ru.mojarung.tramload.domain.agent.ToolSpec;

/** Цикл агента на подставных модели и инструментах: без сети и ключей. */
class AgentServiceTest {

	private static final String SESSION = "session-01";

	@Test
	void answerIsPlainTextWithoutMarkupAndLongDashes() {
		String model = "**Итог:** \u2248 645 посадок\n### Вывод\nпадение \u20111 % \u2014 ночью";

		assertThat(AgentService.plain(model)).isEqualTo("Итог: около 645 посадок\nВывод\nпадение -1 % - ночью");
	}

	@Test
	void toolCallsBecomeStepsUiActionsAndAnAnswerThatIsRemembered() {
		ScriptedModel model = new ScriptedModel(
				calls(new ToolCall("1", "forecast", "{\"level\":\"route\",\"id\":\"17\"}"),
						new ToolCall("2", "ui_show", "{\"route\":17}")),
				text("На 17 маршруте 42 800 посадок, прогноз. Показал на карте."));
		FakeTools tools = new FakeTools();
		FakeMemory memory = new FakeMemory();

		List<AgentEvent> events = service(model, tools, memory).turn(SESSION, "сколько на 17?", Map.of("date", "2025-11-14"))
			.collectList().block();

		assertThat(events).extracting(AgentEvent::type).containsExactly(AgentEvent.Type.STEP, AgentEvent.Type.STEP,
				AgentEvent.Type.UI, AgentEvent.Type.ANSWER);
		assertThat(events.get(2).action()).containsEntry("route", 17);
		assertThat(memory.history(SESSION)).extracting(ChatMessage::role)
			.containsExactly(ChatMessage.Role.SYSTEM, ChatMessage.Role.USER, ChatMessage.Role.ASSISTANT);
		assertThat(model.seen.getFirst().getFirst().content()).contains("date=2025-11-14");
		assertThat(model.seen.get(1)).anySatisfy(m -> assertThat(m.role()).isEqualTo(ChatMessage.Role.TOOL));
	}

	@Test
	void sameDataToolCallIsServedFromCache() {
		ToolCall call = new ToolCall("1", "forecast", "{\"level\":\"network\"}");
		FakeTools tools = new FakeTools();
		AgentService agent = service(new ScriptedModel(calls(call), text("ок"), calls(call), text("ок")), tools,
				new FakeMemory());

		agent.turn(SESSION, "сеть?", Map.of()).blockLast();
		agent.turn(SESSION, "сеть ещё раз?", Map.of()).blockLast();

		assertThat(tools.calls).isEqualTo(1);
	}

	@Test
	void withoutKeyTheAgentSaysItIsNotConfigured() {
		ScriptedModel model = new ScriptedModel();
		model.configured = false;

		List<AgentEvent> events = service(model, new FakeTools(), new FakeMemory()).turn(SESSION, "привет", null)
			.collectList().block();

		assertThat(events).singleElement().satisfies(e -> {
			assertThat(e.type()).isEqualTo(AgentEvent.Type.ERROR);
			assertThat(e.text()).contains("LLM_API_KEY");
		});
	}

	@Test
	void thirteenthQuestionInAMinuteIsRefused() {
		ScriptedModel model = new ScriptedModel();
		for (int i = 0; i < AgentService.SESSION_LIMIT; i++) {
			model.replies.add(text("ок"));
		}
		AgentService agent = service(model, new FakeTools(), new FakeMemory());
		for (int i = 0; i < AgentService.SESSION_LIMIT; i++) {
			agent.turn(SESSION, "вопрос " + i, Map.of()).blockLast();
		}

		AgentEvent refused = agent.turn(SESSION, "ещё", Map.of()).blockLast();

		assertThat(refused.type()).isEqualTo(AgentEvent.Type.ERROR);
		assertThat(refused.text()).contains("подождите минуту");
	}

	@Test
	void sixthRequestSummarisesCollectedDataWithoutToolsAndRemembersTheAnswer() {
		ScriptedModel model = new ScriptedModel();
		for (int i = 0; i < AgentService.MAX_STEPS - 1; i++) {
			model.replies.add(calls(new ToolCall("c" + i, "calendar", "{\"n\":" + i + "}")));
		}
		model.replies.add(text("Проверена только часть недели: 42 800 посадок, прогноз."));
		FakeTools tools = new FakeTools();
		FakeMemory memory = new FakeMemory();

		AgentEvent last = service(model, tools, memory).turn(SESSION, "вопрос", Map.of()).blockLast();

		assertThat(model.seen).hasSize(AgentService.MAX_STEPS);
		assertThat(model.availableTools.getLast()).isEmpty();
		assertThat(model.seen.getLast()).noneMatch(m -> m.role() == ChatMessage.Role.TOOL || !m.toolCalls().isEmpty());
		assertThat(model.seen.getLast().getLast().content()).contains("{\"total\":42800}");
		assertThat(model.seen.getLast().getFirst().content()).contains("Сбор данных завершён", "часть периода");
		assertThat(tools.calls).isEqualTo(5);
		assertThat(last.type()).isEqualTo(AgentEvent.Type.ANSWER);
		assertThat(last.text()).contains("Проверена только часть недели", "42 800");
		assertThat(memory.history(SESSION).getLast().content()).isEqualTo(last.text());
	}

	@Test
	void toolCallOnFinalRequestIsNotExecutedOrReportedAsSuccessfulAnswer() {
		ScriptedModel model = new ScriptedModel();
		for (int i = 0; i < AgentService.MAX_STEPS; i++) {
			model.replies.add(calls(new ToolCall("c" + i, "calendar", "{\"n\":" + i + "}")));
		}
		FakeTools tools = new FakeTools();

		AgentEvent last = service(model, tools, new FakeMemory()).turn(SESSION, "вопрос", Map.of()).blockLast();

		assertThat(model.seen).hasSize(6);
		assertThat(tools.calls).isEqualTo(5);
		assertThat(last.type()).isEqualTo(AgentEvent.Type.ERROR);
	}

	@Test
	void repeatingTheSameUiActionFinalisesEarlyWithoutApplyingItTwice() {
		ScriptedModel model = new ScriptedModel(calls(new ToolCall("a", "ui_show", "{\"route\":17}")),
				calls(new ToolCall("b", "ui_show", "{\"route\":17}")), text("Показал маршрут 17."));
		FakeTools tools = new FakeTools();

		List<AgentEvent> events = service(model, tools, new FakeMemory()).turn(SESSION, "покажи 17", Map.of())
			.collectList().block();

		assertThat(model.seen).hasSize(3);
		assertThat(model.availableTools.getLast()).isEmpty();
		assertThat(tools.calls).isEqualTo(1);
		assertThat(events).filteredOn(e -> e.type() == AgentEvent.Type.UI).hasSize(1);
		assertThat(model.seen.getLast()).noneMatch(m -> m.role() == ChatMessage.Role.TOOL || !m.toolCalls().isEmpty());
		assertThat(model.seen.getLast().getLast().content()).contains("{\"total\":42800}");
	}

	@Test
	void dayQuestionCannotExecuteWeeklyTool() {
		ScriptedModel model = new ScriptedModel(calls(new ToolCall("a", "weekly_load", "{\"date\":\"2027-10-04\"}")),
				calls(new ToolCall("b", "network_load", "{\"date\":\"2027-10-04\"}")), text("Итог за сутки."));
		FakeTools tools = new FakeTools();
		service(model, tools, new FakeMemory()).turn(SESSION, "нагрузка за 4 октября 2027", Map.of("date", "2025-11-16")).blockLast();
		assertThat(tools.calls).isEqualTo(1);
		assertThat(model.seen.get(1)).anySatisfy(m -> assertThat(m.content()).contains("Ошибка периода"));
	}

	@Test
	void unfinishedShowGetsAnotherChanceBeforeAnswer() {
		ScriptedModel model = new ScriptedModel(text("Маршрут 17 самый загруженный."),
				calls(new ToolCall("a", "ui_show", "{\"route\":17}")), text("Показал маршрут 17."));
		List<AgentEvent> events = service(model, new FakeTools(), new FakeMemory())
				.turn(SESSION, "покажи маршрут 17", Map.of()).collectList().block();
		assertThat(events).filteredOn(e -> e.type() == AgentEvent.Type.UI).hasSize(1);
		assertThat(events).filteredOn(e -> e.type() == AgentEvent.Type.ANSWER).hasSize(1);
		assertThat(model.seen).hasSize(3);
	}

	private static AgentService service(LanguageModel model, AgentTools tools, AgentMemory memory) {
		return new AgentService(model, tools, memory, Runnable::run);
	}

	private static ModelReply calls(ToolCall... calls) {
		return new ModelReply(null, List.of(calls));
	}

	private static ModelReply text(String text) {
		return new ModelReply(text, List.of());
	}

	private static final class ScriptedModel implements LanguageModel {

		final Deque<ModelReply> replies = new ArrayDeque<>();
		final List<List<ChatMessage>> seen = new ArrayList<>();
		final List<List<ToolSpec>> availableTools = new ArrayList<>();
		boolean configured = true;

		ScriptedModel(ModelReply... replies) {
			this.replies.addAll(List.of(replies));
		}

		@Override
		public ModelReply complete(List<ChatMessage> messages, List<ToolSpec> tools) {
			seen.add(List.copyOf(messages));
			availableTools.add(List.copyOf(tools));
			return replies.removeFirst();
		}

		@Override
		public boolean configured() {
			return configured;
		}

		@Override
		public String name() {
			return "scripted";
		}

	}

	private static final class FakeTools implements AgentTools {

		int calls;

		@Override
		public List<ToolSpec> specs() {
			return List.of(new ToolSpec("forecast", "прогноз", "{\"type\":\"object\"}"));
		}

		@Override
		public ToolResult call(String name, String argumentsJson) {
			calls++;
			Map<String, Object> ui = name.startsWith("ui_") ? Map.of("type", "show", "route", 17) : null;
			return new ToolResult("{\"total\":42800}", false, ui);
		}

	}

	private static final class FakeMemory implements AgentMemory {

		private final Map<String, List<ChatMessage>> history = new HashMap<>();
		private final Map<String, String> cache = new HashMap<>();
		private final Map<String, Integer> hits = new HashMap<>();

		@Override
		public List<ChatMessage> history(String session) {
			return history.getOrDefault(session, List.of());
		}

		@Override
		public void remember(String session, List<ChatMessage> messages) {
			history.computeIfAbsent(session, k -> new ArrayList<>()).addAll(messages);
		}

		@Override
		public void forget(String session) {
			history.remove(session);
		}

		@Override
		public Optional<String> cached(String key) {
			return Optional.ofNullable(cache.get(key));
		}

		@Override
		public void cache(String key, String value) {
			cache.put(key, value);
		}

		@Override
		public boolean allow(String key, int limit) {
			return hits.merge(key, 1, Integer::sum) <= limit;
		}

		@Override
		public String kind() {
			return "fake";
		}

		@Override
		public boolean healthy() {
			return true;
		}

	}

}
