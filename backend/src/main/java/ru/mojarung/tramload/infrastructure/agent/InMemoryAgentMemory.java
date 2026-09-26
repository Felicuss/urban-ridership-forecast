package ru.mojarung.tramload.infrastructure.agent;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

import ru.mojarung.tramload.domain.agent.AgentMemory;
import ru.mojarung.tramload.domain.agent.ChatMessage;

/**
 * Память агента в процессе: без Redis (разработка, одна реплика). История и кэш живут до перезапуска и
 * у каждой реплики свои; с REDIS_URL вместо неё работает RedisAgentMemory.
 */
final class InMemoryAgentMemory implements AgentMemory {

	private final Cache<String, List<ChatMessage>> history = Caffeine.newBuilder()
		.expireAfterAccess(AgentLimits.HISTORY_TTL).maximumSize(10_000).build();
	private final Cache<String, String> cache = Caffeine.newBuilder()
		.expireAfterWrite(AgentLimits.CACHE_TTL).maximumSize(5_000).build();
	private final ConcurrentMap<String, Integer> hits = new ConcurrentHashMap<>();

	@Override
	public List<ChatMessage> history(String session) {
		return List.copyOf(Optional.ofNullable(history.getIfPresent(session)).orElse(List.of()));
	}

	@Override
	public void remember(String session, List<ChatMessage> messages) {
		history.asMap().compute(session, (k, old) -> {
			List<ChatMessage> all = new ArrayList<>(old == null ? List.of() : old);
			all.addAll(messages);
			return List.copyOf(all.subList(Math.max(0, all.size() - AgentLimits.HISTORY_MAX), all.size()));
		});
	}

	@Override
	public void forget(String session) {
		history.invalidate(session);
	}

	@Override
	public Optional<String> cached(String key) {
		return Optional.ofNullable(cache.getIfPresent(key));
	}

	@Override
	public void cache(String key, String value) {
		cache.put(key, value);
	}

	@Override
	public boolean allow(String key, int limit) {
		String minute = "@" + System.currentTimeMillis() / Duration.ofMinutes(1).toMillis();
		hits.keySet().removeIf(k -> !k.endsWith(minute));
		return hits.merge(key + minute, 1, Integer::sum) <= limit;
	}

	@Override
	public String kind() {
		return "memory";
	}

	@Override
	public boolean healthy() {
		return true;
	}

}
