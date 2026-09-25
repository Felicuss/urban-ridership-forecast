package ru.mojarung.tramload.infrastructure;

/** Каталог artifacts/ не прошёл проверку при старте: сервис с такими данными не запускается. */
public final class ArtifactValidationException extends RuntimeException {

	public ArtifactValidationException(String message) {
		super(message);
	}

	public ArtifactValidationException(String message, Throwable cause) {
		super(message, cause);
	}

}
