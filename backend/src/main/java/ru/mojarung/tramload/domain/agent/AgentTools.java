package ru.mojarung.tramload.domain.agent;

import java.util.List;

/** Инструменты агента (MCP-сервер): описания для модели и вызов по имени. */
public interface AgentTools {

	List<ToolSpec> specs();

	ToolResult call(String name, String argumentsJson);

}
