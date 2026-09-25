package ru.mojarung.tramload.domain;

import java.util.List;
import java.util.stream.Collectors;

/** Запрос или сценарий нарушает область определения модели. Несёт все нарушения сразу, а не первое. */
public final class ValidationException extends RuntimeException {

	private final transient List<Violation> violations;

	public ValidationException(List<Violation> violations) {
		super(violations.stream().map(v -> v.field() + ": " + v.message()).collect(Collectors.joining("; ")));
		this.violations = List.copyOf(violations);
	}

	public static ValidationException of(String field, String message) {
		return new ValidationException(List.of(new Violation(field, message)));
	}

	public List<Violation> violations() {
		return violations;
	}

	public record Violation(String field, String message) {
	}

}
