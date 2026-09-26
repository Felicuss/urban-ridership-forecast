package ru.mojarung.tramload.domain.news;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import java.util.Set;

import org.junit.jupiter.api.Test;

import ru.mojarung.tramload.domain.ScenarioEvent;
import ru.mojarung.tramload.domain.news.DeptransPosts.Post;

/** Сбой из новостей в события сценария и разбор сообщений канала по правилам разметки 2025 года. */
class IncidentImpactTest {

	private static final double ALPHA = 0.5;

	private static Incident incident(String start, String end, List<Integer> routes) {
		return new Incident("23459", routes, OffsetDateTime.parse(start), Optional.ofNullable(end).map(OffsetDateTime::parse),
				IncidentCause.TECHNICAL, "", "https://t.me/DtOperativno/23459", Optional.empty(), Incident.Origin.ARCHIVE);
	}

	@Test
	void partHourUnderIncidentCutsBoardingsInProportion() {
		// 10:28:51-11:09:05: в 10-м часу под сбоем 31,15 мин, в 11-м 9,07 мин
		List<ScenarioEvent> events = IncidentImpact.events(
				incident("2025-11-08T10:28:51+03:00", "2025-11-08T11:09:05+03:00", List.of(12)), ALPHA);

		assertThat(events).hasSize(2);
		assertThat(events.get(0).hours().first()).isEqualTo(10);
		assertThat(events.get(0).multiplier()).isEqualTo(0.740);
		assertThat(events.get(1).hours().first()).isEqualTo(11);
		assertThat(events.get(1).multiplier()).isEqualTo(0.924);
		assertThat(events).allSatisfy(e -> {
			assertThat(e.route().getAsInt()).isEqualTo(12);
			assertThat(e.from()).isEqualTo(LocalDate.of(2025, 11, 8));
			assertThat(e.label()).isEqualTo("сбой 08.11: технические причины");
		});
	}

	@Test
	void fullHoursMergeAndNightIncidentSpillsIntoNextDay() {
		// 16.12 21:55 - 17.12 05:01, как сбой 24137 на маршруте 17
		List<ScenarioEvent> events = IncidentImpact.events(
				incident("2025-12-16T21:55:26+03:00", "2025-12-17T05:01:23+03:00", List.of(17)), ALPHA);

		assertThat(events).extracting(e -> e.from() + " " + e.hours() + " x" + e.multiplier()).containsExactly(
				"2025-12-16 21-21 x0.962", "2025-12-16 22-23 x0.5", "2025-12-17 0-4 x0.5", "2025-12-17 5-5 x0.988");
	}

	@Test
	void everyRouteGetsItsOwnEventsAndTryOnMovesTheDay() {
		List<ScenarioEvent> events = IncidentImpact.events(
				incident("2025-08-09T22:50:56+03:00", "2025-08-09T23:12:42+03:00", List.of(11, 12)), ALPHA,
				LocalDate.of(2025, 11, 14));

		// 22:50-23:12 задевает два часа, у каждого маршрута свои события
		assertThat(events).extracting(e -> e.route().getAsInt()).containsExactly(11, 11, 12, 12);
		assertThat(events).allSatisfy(e -> {
			assertThat(e.from()).isEqualTo(LocalDate.of(2025, 11, 14));
			assertThat(e.hours().first()).isIn(22, 23);
			assertThat(e.label()).startsWith("как сбой 09.08");
		});
	}

	@Test
	void ongoingIncidentHasNoEventsAndEndMustFollowStart() {
		assertThat(IncidentImpact.events(incident("2025-11-08T10:28:51+03:00", null, List.of(12)), ALPHA)).isEmpty();
		assertThatThrownBy(() -> incident("2025-11-08T10:28:51+03:00", "2025-11-08T10:00:00+03:00", List.of(12)))
			.isInstanceOf(IllegalArgumentException.class);
	}

	@Test
	void channelPostsPairIntoIncidentsForForecastRoutesOnly() {
		OffsetDateTime t = OffsetDateTime.parse("2025-11-08T07:28:51Z");
		List<Post> posts = List.of(
				new Post("DtOperativno/23459", t, Optional.empty(), "В районе Авиамоторной улицы по техническим причинам "
						+ "задерживаются трамваи № 2, 12, 36 и 37. Маршруты временно изменены."),
				new Post("DtOperativno/23460", t.plusMinutes(40), Optional.of("DtOperativno/23459"),
						"Восстановлено движение трамваев на Авиамоторной улице."),
				new Post("DtOperativno/23455", t.minusHours(14), Optional.empty(),
						"На улице Маши Порываевой из-за ДТП задерживаются трамваи № 90."),
				new Post("DtOperativno/23470", t.plusMinutes(50), Optional.empty(),
						"На проспекте Мира из-за обрыва контактной сети задерживаются трамваи № 17."));

		List<Incident> incidents = DeptransPosts.incidents(posts, Set.of(1, 12, 17), t.plusHours(1));

		assertThat(incidents).extracting(Incident::id).containsExactly("23470", "23459");
		Incident closed = incidents.get(1);
		assertThat(closed.routes()).containsExactly(12);
		assertThat(closed.minutes()).contains(40.0);
		assertThat(closed.location()).isEqualTo("В районе Авиамоторной улицы по техническим причинам");
		assertThat(closed.recoveryUrl()).contains("https://t.me/DtOperativno/23460");
		Incident open = incidents.get(0);
		assertThat(open.ongoing()).isTrue();
		assertThat(open.cause()).isEqualTo(IncidentCause.CONTACT_NETWORK);
	}

	@Test
	void incidentWithoutRecoveryForADayIsDropped() {
		OffsetDateTime t = OffsetDateTime.parse("2025-11-08T07:28:51Z");
		List<Post> posts = List.of(new Post("DtOperativno/1", t, Optional.empty(), "Из-за ДТП задерживаются трамваи № 17."));

		assertThat(DeptransPosts.incidents(posts, Set.of(17), t.plusDays(2))).isEmpty();
	}

}
