package ru.mojarung.tramload.api.security;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.password.PasswordEncoder;

/**
 * Учётные записи из настройки «логин:пароль:имя,логин:пароль:имя». Пароль сразу превращается в хеш bcrypt,
 * открытым текстом он в памяти не остаётся. Ошибка в настройке останавливает запуск с понятным текстом.
 */
public final class Accounts {

	static final String ROLE = "DISPATCHER";

	private final Map<String, String> names;
	private final MapReactiveUserDetailsService users;

	private Accounts(Map<String, String> names, List<UserDetails> users) {
		this.names = Map.copyOf(names);
		this.users = new MapReactiveUserDetailsService(users);
	}

	public static Accounts parse(String spec, PasswordEncoder encoder) {
		Map<String, String> names = new LinkedHashMap<>();
		List<UserDetails> users = new ArrayList<>();
		for (String entry : spec.split(",")) {
			if (entry.isBlank()) {
				continue;
			}
			String[] parts = entry.trim().split(":", 3);
			if (parts.length < 2 || parts[0].isBlank() || parts[1].isBlank()) {
				throw new IllegalStateException("AUTH_USERS: запись «" + parts[0]
						+ "» должна иметь вид логин:пароль или логин:пароль:имя");
			}
			String login = parts[0].trim();
			if (names.containsKey(login)) {
				throw new IllegalStateException("AUTH_USERS: логин " + login + " указан дважды");
			}
			names.put(login, parts.length == 3 && !parts[2].isBlank() ? parts[2].trim() : login);
			users.add(User.withUsername(login).password(encoder.encode(parts[1])).roles(ROLE).build());
		}
		if (users.isEmpty()) {
			throw new IllegalStateException("AUTH_USERS пуст: задайте хотя бы одну запись логин:пароль");
		}
		return new Accounts(names, users);
	}

	public MapReactiveUserDetailsService userDetails() {
		return users;
	}

	/** Имя для верхней строки интерфейса; для неизвестного логина - пусто. */
	public Optional<String> name(String login) {
		return Optional.ofNullable(names.get(login));
	}

}
