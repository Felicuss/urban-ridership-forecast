package ru.mojarung.tramload.api.dto;

/** Начать диалог заново: история сессии удаляется. */
public record AgentResetRequest(String session) {
}
