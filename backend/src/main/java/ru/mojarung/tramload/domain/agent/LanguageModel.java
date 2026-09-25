package ru.mojarung.tramload.domain.agent;

import java.util.List;

/** Языковая модель с вызовом инструментов. Ошибку связи сообщает через AgentFailure. */
public interface LanguageModel {

	ModelReply complete(List<ChatMessage> messages, List<ToolSpec> tools);

	boolean configured();

	String name();

}
