package ru.mojarung.tramload.infrastructure.agent;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.Executors;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

import tools.jackson.databind.json.JsonMapper;

import ru.mojarung.tramload.domain.agent.AgentMemory;
import ru.mojarung.tramload.domain.agent.AgentTools;
import ru.mojarung.tramload.domain.agent.ChatMessage;
import ru.mojarung.tramload.domain.agent.LanguageModel;
import ru.mojarung.tramload.domain.agent.ModelReply;
import ru.mojarung.tramload.domain.agent.ToolSpec;

/**
 * Агент: модель (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL), инструменты MCP-сервера (MCP_URL) и память (REDIS_URL).
 * Без ключа модели агент отвечает «не настроен», без Redis память живёт в процессе.
 */
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(AgentConfiguration.AgentProperties.class)
public class AgentConfiguration {

	@ConfigurationProperties("tramload.agent")
	public record AgentProperties(String llmBaseUrl, String llmApiKey, String llmModel, Duration llmTimeout, String mcpUrl,
			Duration mcpTimeout, String redisUrl) {

		public AgentProperties {
			llmBaseUrl = llmBaseUrl == null || llmBaseUrl.isBlank() ? "https://ollama.com/v1" : llmBaseUrl;
			llmModel = llmModel == null || llmModel.isBlank() ? "gpt-oss:120b" : llmModel;
			llmTimeout = llmTimeout == null ? Duration.ofSeconds(60) : llmTimeout;
			mcpUrl = mcpUrl == null || mcpUrl.isBlank() ? "http://localhost:8765/mcp" : mcpUrl;
			mcpTimeout = mcpTimeout == null ? Duration.ofSeconds(20) : mcpTimeout;
		}

	}

	private static final JsonMapper JSON = JsonMapper.builder().build();

	@Bean
	HttpClient agentHttpClient() {
		return HttpClient.newBuilder()
			.connectTimeout(Duration.ofSeconds(5))
			.executor(Executors.newVirtualThreadPerTaskExecutor())
			.build();
	}

	@Bean
	LanguageModel languageModel(AgentProperties p, HttpClient agentHttpClient) {
		if (p.llmApiKey() == null || p.llmApiKey().isBlank()) {
			return new Unconfigured(p.llmModel());
		}
		return new OpenAiCompatibleModel(agentHttpClient, JSON, p.llmBaseUrl(), p.llmApiKey(), p.llmModel(), p.llmTimeout());
	}

	@Bean
	AgentTools agentTools(AgentProperties p, HttpClient agentHttpClient) {
		return new McpHttpTools(agentHttpClient, JSON, p.mcpUrl(), p.mcpTimeout());
	}

	@Bean
	AgentMemory agentMemory(AgentProperties p, ObjectProvider<StringRedisTemplate> redis) {
		StringRedisTemplate template = redis.getIfAvailable();
		boolean useRedis = p.redisUrl() != null && !p.redisUrl().isBlank() && template != null;
		return useRedis ? new RedisAgentMemory(template, JSON) : new InMemoryAgentMemory();
	}

	/** Модель без ключа: агент сразу отвечает, что не настроен, и не ходит в сеть. */
	private record Unconfigured(String name) implements LanguageModel {

		@Override
		public ModelReply complete(List<ChatMessage> messages, List<ToolSpec> tools) {
			throw new IllegalStateException("модель не настроена");
		}

		@Override
		public boolean configured() {
			return false;
		}

	}

}
