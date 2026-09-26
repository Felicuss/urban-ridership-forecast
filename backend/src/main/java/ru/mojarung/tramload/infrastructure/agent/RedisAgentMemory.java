package ru.mojarung.tramload.infrastructure.agent;

import java.time.Duration;
import java.util.List;
import java.util.Optional;
import java.util.function.Supplier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.json.JsonMapper;

import ru.mojarung.tramload.domain.agent.AgentMemory;
import ru.mojarung.tramload.domain.agent.ChatMessage;

/**
 * Память агента в Redis: история диалога общая для реплик и переживает перезапуск, кэш ответов инструментов
 * и лимит запросов к модели тоже общие. Если Redis недоступен, агент работает дальше: без истории и кэша,
 * а лимит пропускает запрос - ответ важнее учёта.
 */
final class RedisAgentMemory implements AgentMemory {

	private static final Logger log = LoggerFactory.getLogger(RedisAgentMemory.class);

	private final StringRedisTemplate redis;
	private final JsonMapper json;

	RedisAgentMemory(StringRedisTemplate redis, JsonMapper json) {
		this.redis = redis;
		this.json = json;
	}

	@Override
	public List<ChatMessage> history(String session) {
		List<String> raw = safe(() -> redis.opsForList().range(historyKey(session), 0, -1), List.of());
		return raw == null ? List.of() : raw.stream().map(this::read).flatMap(Optional::stream).toList();
	}

	@Override
	public void remember(String session, List<ChatMessage> messages) {
		String key = historyKey(session);
		safe(() -> {
			redis.opsForList().rightPushAll(key, messages.stream().map(json::writeValueAsString).toList());
			redis.opsForList().trim(key, -AgentLimits.HISTORY_MAX, -1);
			return redis.expire(key, AgentLimits.HISTORY_TTL);
		}, null);
	}

	@Override
	public void forget(String session) {
		safe(() -> redis.delete(historyKey(session)), null);
	}

	@Override
	public Optional<String> cached(String key) {
		return Optional.ofNullable(safe(() -> redis.opsForValue().get("agent:cache:" + key), null));
	}

	@Override
	public void cache(String key, String value) {
		safe(() -> {
			redis.opsForValue().set("agent:cache:" + key, value, AgentLimits.CACHE_TTL);
			return null;
		}, null);
	}

	@Override
	public boolean allow(String key, int limit) {
		String window = "agent:rate:" + key + ":" + System.currentTimeMillis() / Duration.ofMinutes(1).toMillis();
		Long hits = safe(() -> {
			Long n = redis.opsForValue().increment(window);
			redis.expire(window, Duration.ofMinutes(1));
			return n;
		}, null);
		return hits == null || hits <= limit;
	}

	@Override
	public String kind() {
		return "redis";
	}

	@Override
	public boolean healthy() {
		return Boolean.TRUE.equals(safe(() -> "PONG".equals(redis.execute((RedisCallback<String>) RedisConnection::ping)), false));
	}

	private Optional<ChatMessage> read(String raw) {
		try {
			return Optional.of(json.readValue(raw, ChatMessage.class));
		}
		catch (JacksonException e) {
			log.warn("в истории агента запись не читается, пропускаю: {}", e.getOriginalMessage());
			return Optional.empty();
		}
	}

	private static String historyKey(String session) {
		return "agent:history:" + session;
	}

	private static <T> T safe(Supplier<T> call, T fallback) {
		try {
			return call.get();
		}
		catch (DataAccessException e) {
			log.warn("Redis недоступен, агент работает без него: {}", e.getMessage());
			return fallback;
		}
	}

}
