package ru.mojarung.tramload.api.dto;

/** Кто вошёл: логин и имя для верхней строки; authRequired - включён ли вход в сервисе. */
public record UserDto(String username, String name, boolean authRequired) {
}
