package ru.mojarung.tramload.domain.agent;

import java.util.Map;

/**
 * Событие хода агента для интерфейса: step - какой инструмент вызван, ui - команда интерфейсу,
 * answer - ответ, error - почему ответа нет.
 */
public record AgentEvent(Type type, String text, String tool, Map<String, Object> action) {

	public enum Type {
		STEP, UI, ANSWER, ERROR
	}

	public static AgentEvent step(String tool, String text) {
		return new AgentEvent(Type.STEP, text, tool, null);
	}

	public static AgentEvent ui(String tool, Map<String, Object> action) {
		return new AgentEvent(Type.UI, null, tool, action);
	}

	public static AgentEvent answer(String text) {
		return new AgentEvent(Type.ANSWER, text, null, null);
	}

	public static AgentEvent error(String text) {
		return new AgentEvent(Type.ERROR, text, null, null);
	}

}
