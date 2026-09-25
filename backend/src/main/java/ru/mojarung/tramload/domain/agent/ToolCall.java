package ru.mojarung.tramload.domain.agent;

/** Вызов инструмента, который попросила модель: аргументы - JSON-строка как есть. */
public record ToolCall(String id, String name, String arguments) {
}
