package ru.mojarung.tramload.domain.agent;

import java.util.List;
import java.util.Optional;

/** История диалогов, кэш ответов инструментов и лимит запросов (Redis или память процесса). */
public interface AgentMemory {

	List<ChatMessage> history(String session);

	void remember(String session, List<ChatMessage> messages);

	void forget(String session);

	Optional<String> cached(String key);

	void cache(String key, String value);

	/** Можно ли ещё один запрос по ключу в текущую минуту при лимите limit. */
	boolean allow(String key, int limit);

	String kind();

	boolean healthy();

}
