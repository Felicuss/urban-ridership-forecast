package ru.mojarung.tramload.api.dto;

/** Объект ряда. estimate = true для остановок и участков: это раскладка маршрута по долям. */
public record TargetDto(String level, String id, String name, boolean estimate) {
}
