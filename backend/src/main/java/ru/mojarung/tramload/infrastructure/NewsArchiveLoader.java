package ru.mojarung.tramload.infrastructure;

import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import tools.jackson.databind.JsonNode;

import ru.mojarung.tramload.domain.news.Incident;
import ru.mojarung.tramload.domain.news.IncidentCause;
import ru.mojarung.tramload.domain.news.NewsArchive;

/** Читает artifacts/news.json (контракт - analysis/export_news.py). Файл уже сверен с manifest.json. */
public final class NewsArchiveLoader {

	private NewsArchiveLoader() {
	}

	public static NewsArchive load(Path dir) {
		JsonNode news = ArtifactLoader.readJson(dir.resolve("news.json"));
		try {
			List<Incident> incidents = new ArrayList<>();
			for (JsonNode n : news.path("incidents")) {
				List<Integer> routes = new ArrayList<>();
				n.path("routes").forEach(r -> routes.add(r.asInt()));
				String recovery = n.path("recovery_url").asString("");
				incidents.add(new Incident(n.path("id").asString(), routes, OffsetDateTime.parse(n.path("start").asString()),
						Optional.of(OffsetDateTime.parse(n.path("end").asString())), IncidentCause.of(n.path("cause").asString()),
						n.path("location").asString(""), n.path("source_url").asString(),
						recovery.isBlank() ? Optional.empty() : Optional.of(recovery), Incident.Origin.ARCHIVE));
			}
			return new NewsArchive(news.path("channel").asString(), news.path("alpha").asDouble(),
					news.path("alpha_source").asString(""), incidents);
		}
		catch (RuntimeException ex) {
			throw new ArtifactValidationException("news.json не разобран: " + ex.getMessage(), ex);
		}
	}

}
