package ru.mojarung.tramload.infrastructure.agent;

import java.time.Duration;

/** Сроки памяти агента: история диалога сутки, кэш ответов инструментов 10 минут, 16 последних реплик. */
final class AgentLimits {

	static final Duration HISTORY_TTL = Duration.ofHours(24);
	static final Duration CACHE_TTL = Duration.ofMinutes(10);
	static final int HISTORY_MAX = 16;

	private AgentLimits() {
	}

}
