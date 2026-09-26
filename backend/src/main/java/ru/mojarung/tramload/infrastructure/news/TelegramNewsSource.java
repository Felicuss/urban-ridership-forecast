package ru.mojarung.tramload.infrastructure.news;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.Set;

import org.jsoup.Jsoup;
import org.jsoup.nodes.Element;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import ru.mojarung.tramload.domain.news.DeptransPosts;
import ru.mojarung.tramload.domain.news.DeptransPosts.Post;
import ru.mojarung.tramload.domain.news.NewsSource;

/**
 * Живая лента канала Дептранса: публичная веб-версия t.me/s/DtOperativno, последние 20 сообщений. Читается
 * не чаще раза в refresh; если канал недоступен, отдаётся прошлый результат с текстом ошибки.
 */
public final class TelegramNewsSource implements NewsSource {

	private static final Logger LOG = LoggerFactory.getLogger(TelegramNewsSource.class);
	private static final String REPLY_PREFIX = "https://t.me/";

	private final HttpClient http;
	private final URI url;
	private final Duration refresh;
	private final Duration timeout;
	private final Set<Integer> routes;
	private final Clock clock;
	private LiveNews last = LiveNews.off();
	private Instant fetchedAt = Instant.MIN;

	public TelegramNewsSource(HttpClient http, URI url, Duration refresh, Duration timeout, Set<Integer> routes,
			Clock clock) {
		this.http = http;
		this.url = url;
		this.refresh = refresh;
		this.timeout = timeout;
		this.routes = Set.copyOf(routes);
		this.clock = clock;
	}

	@Override
	public synchronized LiveNews latest() {
		Instant now = clock.instant();
		if (fetchedAt.plus(refresh).isAfter(now)) {
			return last;
		}
		fetchedAt = now;
		try {
			List<Post> posts = posts(fetch());
			last = new LiveNews(DeptransPosts.incidents(posts, routes, OffsetDateTime.now(clock)), Optional.of(now),
					Optional.empty());
		}
		catch (IOException | RuntimeException ex) {
			LOG.warn("лента {} не прочитана: {}", url, ex.toString());
			last = new LiveNews(last.incidents(), Optional.of(now), Optional.of("лента канала недоступна"));
		}
		catch (InterruptedException ex) {
			Thread.currentThread().interrupt();
			last = new LiveNews(last.incidents(), Optional.of(now), Optional.of("чтение ленты прервано"));
		}
		return last;
	}

	private String fetch() throws IOException, InterruptedException {
		HttpRequest request = HttpRequest.newBuilder(url).timeout(timeout).header("User-Agent", "Mozilla/5.0 chaspik").GET()
			.build();
		HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
		if (response.statusCode() >= 400) {
			throw new IOException("канал ответил " + response.statusCode());
		}
		return response.body();
	}

	/** Текст сообщения берётся из js-message_text: цитата родителя в ответе лежит в другом блоке. */
	static List<Post> posts(String html) {
		List<Post> out = new ArrayList<>();
		for (Element m : Jsoup.parse(html).select(".tgme_widget_message[data-post]")) {
			Element text = m.selectFirst(".js-message_text");
			Element time = m.selectFirst("time[datetime]");
			if (text == null || time == null) {
				continue;
			}
			Element reply = m.selectFirst("a.tgme_widget_message_reply");
			Optional<String> replyTo = Optional.ofNullable(reply)
				.map(r -> r.attr("href"))
				.filter(h -> h.startsWith(REPLY_PREFIX))
				.map(h -> h.substring(REPLY_PREFIX.length()));
			try {
				out.add(new Post(m.attr("data-post"), OffsetDateTime.parse(time.attr("datetime")), replyTo, text.text()));
			}
			catch (DateTimeParseException ex) {
				LOG.debug("сообщение {} без даты: {}", m.attr("data-post"), ex.getMessage());
			}
		}
		return out;
	}

}
