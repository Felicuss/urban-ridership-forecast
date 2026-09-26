package ru.mojarung.tramload.domain.news;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.function.Function;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * Сообщения канала Дептранса в сбои. Правила те же, что в analysis/s45_incident_adjustment.py: сбой - это
 * сообщение «задерживаются трамваи №…» с маршрутами из прогноза; конец - ответ на него «восстановлено
 * движение трамваев» в пределах суток. Сбой без ответа остаётся открытым.
 */
public final class DeptransPosts {

	private static final String CHANNEL = "https://t.me/";
	private static final Pattern ROUTE_LIST = Pattern.compile("№\\s*([^.]+)");
	private static final Pattern NUMBER = Pattern.compile("\\b\\d+\\b");
	private static final Duration MAX_DURATION = Duration.ofDays(1);

	/**
	 * Сообщение канала.
	 *
	 * @param id номер вида DtOperativno/23459
	 * @param replyTo номер сообщения, на которое это ответ
	 */
	public record Post(String id, OffsetDateTime published, Optional<String> replyTo, String text) {
	}

	private DeptransPosts() {
	}

	public static List<Incident> incidents(List<Post> posts, Set<Integer> routes, OffsetDateTime now) {
		Map<String, Post> byId = posts.stream().collect(Collectors.toMap(Post::id, Function.identity(), (a, b) -> a));
		Map<String, Post> recoveries = posts.stream()
			.filter(p -> p.replyTo().isPresent() && p.text().toLowerCase(Locale.ROOT).contains("восстановлено движение трамва"))
			.collect(Collectors.toMap(p -> p.replyTo().get(), Function.identity(), (a, b) -> a));
		List<Incident> out = new ArrayList<>();
		for (Post post : byId.values()) {
			if (!post.text().contains("задерживаются трамваи")) {
				continue;
			}
			List<Integer> own = routes(post.text(), routes);
			if (own.isEmpty()) {
				continue;
			}
			Optional<Post> recovery = Optional.ofNullable(recoveries.get(post.id()))
				.filter(r -> r.published().isAfter(post.published())
						&& Duration.between(post.published(), r.published()).compareTo(MAX_DURATION) < 0);
			// без ответа дольше суток сбой считается потерянным, а не идущим: такие не показываются
			if (recovery.isEmpty() && Duration.between(post.published(), now).compareTo(MAX_DURATION) >= 0) {
				continue;
			}
			out.add(new Incident(post.id().substring(post.id().lastIndexOf('/') + 1), own, post.published(),
					recovery.map(Post::published), IncidentCause.classify(post.text()), location(post.text()),
					CHANNEL + post.id(), recovery.map(r -> CHANNEL + r.id()), Incident.Origin.LIVE));
		}
		out.sort(Comparator.comparing(Incident::start).reversed());
		return out;
	}

	/** Маршруты из перечня после «№»: только те, что есть в прогнозе, по возрастанию. */
	static List<Integer> routes(String text, Set<Integer> known) {
		Matcher list = ROUTE_LIST.matcher(text);
		if (!list.find()) {
			return List.of();
		}
		Set<Integer> found = new LinkedHashSet<>();
		Matcher n = NUMBER.matcher(list.group(1));
		while (n.find()) {
			int route = Integer.parseInt(n.group());
			if (known.contains(route)) {
				found.add(route);
			}
		}
		return found.stream().sorted().toList();
	}

	/** Место - начало сообщения до слов «задерживаются трамваи». */
	static String location(String text) {
		int at = text.indexOf("задерживаются");
		return (at > 0 ? text.substring(0, at) : text).strip();
	}

}
