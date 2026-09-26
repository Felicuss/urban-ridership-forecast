package ru.mojarung.tramload.infrastructure.news;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;

import ru.mojarung.tramload.domain.news.DeptransPosts.Post;

/** Разбор веб-версии канала: текст ответа берётся из тела сообщения, а не из цитаты родителя. */
class TelegramNewsSourceTest {

	private static final String PAGE = """
			<div class="tgme_widget_message_wrap"><div class="tgme_widget_message js-widget_message" data-post="DtOperativno/23459">
			  <div class="tgme_widget_message_text js-message_text" dir="auto">В районе Авиамоторной улицы по техническим
			  причинам задерживаются трамваи № 2, 12, 36 и 37.</div>
			  <a class="tgme_widget_message_date"><time datetime="2025-11-08T07:28:51+00:00" class="time">07:28</time></a>
			</div></div>
			<div class="tgme_widget_message_wrap"><div class="tgme_widget_message js-widget_message" data-post="DtOperativno/23460">
			  <a class="tgme_widget_message_reply user-color-default" href="https://t.me/DtOperativno/23459">
			    <div class="tgme_widget_message_text js-message_reply_text" dir="auto">задерживаются трамваи № 12</div>
			  </a>
			  <div class="tgme_widget_message_text js-message_text" dir="auto">Восстановлено движение трамваев &quot;на
			  Авиамоторной&quot; улице.</div>
			  <a class="tgme_widget_message_date"><time datetime="2025-11-08T08:09:05+00:00" class="time">08:09</time></a>
			</div></div>
			<div class="tgme_widget_message js-widget_message" data-post="DtOperativno/23461"><div class="photo"></div></div>
			""";

	@Test
	void readsBodyTextReplyAndTimeOfEveryMessage() {
		List<Post> posts = TelegramNewsSource.posts(PAGE);

		assertThat(posts).hasSize(2);
		assertThat(posts.get(0).id()).isEqualTo("DtOperativno/23459");
		assertThat(posts.get(0).replyTo()).isEmpty();
		assertThat(posts.get(0).text()).startsWith("В районе Авиамоторной").contains("задерживаются трамваи № 2, 12");
		Post reply = posts.get(1);
		assertThat(reply.replyTo()).contains("DtOperativno/23459");
		assertThat(reply.text()).isEqualTo("Восстановлено движение трамваев \"на Авиамоторной\" улице.");
		assertThat(reply.published()).hasToString("2025-11-08T08:09:05Z");
	}

}
