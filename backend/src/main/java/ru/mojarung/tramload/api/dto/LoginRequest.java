package ru.mojarung.tramload.api.dto;

/** Логин и пароль диспетчера. */
public record LoginRequest(String username, String password) {
}
