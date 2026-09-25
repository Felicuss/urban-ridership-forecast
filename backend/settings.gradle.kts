plugins {
	// JDK 25 для toolchain скачивается автоматически, если его нет на машине
	id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}

rootProject.name = "tram-load-api"
