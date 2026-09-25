package ru.mojarung.tramload.domain.agent;

/** Модель или инструменты недоступны: сеть, тайм-аут, ответ не по протоколу. */
public final class AgentFailure extends RuntimeException {

	private static final long serialVersionUID = 1L;

	public AgentFailure(String message, Throwable cause) {
		super(message, cause);
	}

	public AgentFailure(String message) {
		super(message);
	}

}
