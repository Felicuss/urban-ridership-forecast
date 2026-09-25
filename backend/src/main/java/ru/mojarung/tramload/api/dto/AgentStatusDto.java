package ru.mojarung.tramload.api.dto;

/** Настроен ли агент: есть ли ключ модели, какая модель и где память (redis или memory). */
public record AgentStatusDto(boolean configured, String model, String memory, boolean memoryHealthy) {
}
