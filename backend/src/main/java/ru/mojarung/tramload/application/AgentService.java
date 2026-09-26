package ru.mojarung.tramload.application;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Executor;
import java.util.function.Consumer;
import java.util.regex.Pattern;

import reactor.core.publisher.Flux;
import ru.mojarung.tramload.domain.agent.AgentEvent;
import ru.mojarung.tramload.domain.agent.AgentFailure;
import ru.mojarung.tramload.domain.agent.AgentMemory;
import ru.mojarung.tramload.domain.agent.AgentTools;
import ru.mojarung.tramload.domain.agent.ChatMessage;
import ru.mojarung.tramload.domain.agent.LanguageModel;
import ru.mojarung.tramload.domain.agent.ModelReply;
import ru.mojarung.tramload.domain.agent.ToolCall;
import ru.mojarung.tramload.domain.agent.ToolResult;
import ru.mojarung.tramload.domain.agent.ToolSpec;

/**
 * ReAct-агент диспетчера: модель думает, вызывает инструменты MCP-сервера и отвечает. Ход агента - поток событий
 * для интерфейса: какой инструмент вызван, команды интерфейсу, ответ или причина, почему ответа нет. Цикл
 * синхронный и идёт на виртуальном потоке: модель и инструменты - сетевые вызовы, поток Netty они не держат.
 */
public final class AgentService {

	public static final int MAX_STEPS = 6;
	public static final int MAX_INPUT = 1000;
	static final int MAX_TOOL_CHARS = 6000;
	static final int SESSION_LIMIT = 12;
	static final int GLOBAL_LIMIT = 60;
	private static final Set<String> UI_TOOLS = Set.of("ui_show", "ui_layers", "ui_ride");
	/** Жирный из звёздочек и подчёркиваний, решётки заголовков в начале строки. */
	private static final Pattern MARKUP = Pattern.compile("\\*\\*|__|(?m)^#{1,6}\\s+");
	private static final Map<String, String> STEP_TEXT = Map.ofEntries(Map.entry("model_info", "Смотрю паспорт модели"),
			Map.entry("list_routes", "Смотрю маршруты"), Map.entry("find_stops", "Ищу остановку"),
			Map.entry("forecast", "Считаю прогноз"), Map.entry("network_load", "Смотрю загрузку сети"),
			Map.entry("scenario", "Пересчитываю сценарий"), Map.entry("coefficients_catalog", "Смотрю ползунки"),
			Map.entry("calendar", "Смотрю календарь"), Map.entry("export_link", "Готовлю выгрузку"),
			Map.entry("ui_show", "Показываю на экране"), Map.entry("ui_layers", "Меняю слои карты"),
			Map.entry("ui_ride", "Запускаю трамвай"), Map.entry("transport_news", "Читаю новости Дептранса"),
			Map.entry("news_events", "Переношу сбой в сценарий"));

	private final LanguageModel model;
	private final AgentTools tools;
	private final AgentMemory memory;
	private final Executor executor;

	public AgentService(LanguageModel model, AgentTools tools, AgentMemory memory, Executor executor) {
		this.model = model;
		this.tools = tools;
		this.memory = memory;
		this.executor = executor;
	}

	/** Ход агента потоком событий; поток всегда завершается, ошибка приходит событием error. */
	public Flux<AgentEvent> turn(String session, String message, Map<String, Object> context) {
		return Flux.create(sink -> executor.execute(() -> {
			try {
				run(session, message, context, sink::next);
			}
			catch (AgentFailure e) {
				sink.next(AgentEvent.error("Модель или инструменты не ответили: " + e.getMessage()
						+ ". Повторите через минуту."));
			}
			sink.complete();
		}));
	}

	public void reset(String session) {
		memory.forget(session);
	}

	public Status status() {
		return new Status(model.configured(), model.name(), memory.kind(), memory.healthy());
	}

	public record Status(boolean configured, String model, String memory, boolean memoryHealthy) {
	}

	void run(String session, String message, Map<String, Object> context, Consumer<AgentEvent> emit) {
		String problem = reject(session, message);
		if (problem != null) {
			emit.accept(AgentEvent.error(problem));
			return;
		}
		List<ChatMessage> messages = new ArrayList<>();
		messages.add(ChatMessage.system(AgentPrompt.system(context)));
		messages.addAll(memory.history(session));
		messages.add(ChatMessage.user(message));
		List<ToolSpec> specs = tools.specs();
		for (int step = 0; step < MAX_STEPS; step++) {
			ModelReply reply = model.complete(messages, specs);
			if (!reply.wantsTools()) {
				String answer = reply.content() == null || reply.content().isBlank()
						? "Не нашёл, что ответить: уточните вопрос." : plain(reply.content());
				memory.remember(session, List.of(ChatMessage.user(message), ChatMessage.assistant(answer)));
				emit.accept(AgentEvent.answer(answer));
				return;
			}
			messages.add(ChatMessage.calls(reply.content(), reply.toolCalls()));
			for (ToolCall call : reply.toolCalls()) {
				messages.add(ChatMessage.tool(call.id(), callTool(call, emit)));
			}
		}
		emit.accept(AgentEvent.answer("Не уложился в шесть шагов. Уточните, что именно показать или посчитать."));
	}

	private String reject(String session, String message) {
		if (!model.configured()) {
			return "Агент не настроен: нет ключа LLM_API_KEY. Впишите ключ Ollama Cloud (ollama.com/settings/keys) "
					+ "в .env и перезапустите сервис: docker compose up -d.";
		}
		if (message == null || message.isBlank()) {
			return "Пустой вопрос.";
		}
		if (message.length() > MAX_INPUT) {
			return "Вопрос длиннее " + MAX_INPUT + " символов: сократите его.";
		}
		if (!memory.allow("session:" + session, SESSION_LIMIT) || !memory.allow("all", GLOBAL_LIMIT)) {
			return "Слишком много вопросов подряд: подождите минуту.";
		}
		return null;
	}

	/** Вызов инструмента с событиями; ответы с данными кэшируются, команды интерфейсу - нет. */
	private String callTool(ToolCall call, Consumer<AgentEvent> emit) {
		emit.accept(AgentEvent.step(call.name(), STEP_TEXT.getOrDefault(call.name(), "Вызываю " + call.name())));
		boolean ui = UI_TOOLS.contains(call.name());
		String key = "tool:" + sha1(call.name() + ":" + call.arguments());
		if (!ui) {
			var hit = memory.cached(key);
			if (hit.isPresent()) {
				return hit.get();
			}
		}
		ToolResult result = tools.call(call.name(), call.arguments());
		if (ui && !result.error() && result.ui() != null) {
			emit.accept(AgentEvent.ui(call.name(), result.ui()));
		}
		String text = result.error() ? "Ошибка: " + result.text() : result.text();
		String cut = text.length() > MAX_TOOL_CHARS ? text.substring(0, MAX_TOOL_CHARS) : text;
		if (!ui && !result.error()) {
			memory.cache(key, cut);
		}
		return cut;
	}

	/**
	 * Ответ модели в простой текст, как пишет весь интерфейс: длинное тире и неразрывный дефис - обычным
	 * дефисом, знак «≈» - словом «около», разметка жирного и заголовков убирается.
	 */
	static String plain(String text) {
		return MARKUP.matcher(text.strip()).replaceAll("")
			.replace('\u2014', '-')
			.replace('\u2013', '-')
			.replace('\u2011', '-')
			.replace("\u2248 ", "около ")
			.replace("\u2248", "около ");
	}

	private static String sha1(String text) {
		try {
			return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-1").digest(text.getBytes(StandardCharsets.UTF_8)));
		}
		catch (NoSuchAlgorithmException e) {
			throw new IllegalStateException("в JDK нет SHA-1", e);
		}
	}

}
