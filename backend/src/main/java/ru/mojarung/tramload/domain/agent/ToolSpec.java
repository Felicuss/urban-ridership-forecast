package ru.mojarung.tramload.domain.agent;

/** Описание инструмента для модели: имя, назначение и JSON Schema аргументов. */
public record ToolSpec(String name, String description, String parametersJson) {
}
