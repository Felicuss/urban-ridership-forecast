import { useState } from 'react';
import type { ScenarioEvent } from '../../api/types';
import { useNewsFeed, type NewsIncident } from '../../hooks/useNews';
import { MAX_EVENTS, useStore } from '../../state/store';
import { HORIZON_END, HORIZON_START, dayIndex, isoDate, shortDate } from '../../lib/time';
import { fmt1 } from '../../lib/format';
import { routeColor } from '../../lib/routes';
import { InfoTip, TramDots } from '../ui/Controls';
import { Icon } from '../ui/Icons';
import styles from './Panels.module.css';

// Сбои из оперативных новостей Дептранса как события сценария. Сервис сам читает канал и разбирает пары
// «задерживаются трамваи» - «движение восстановлено»; здесь сбой можно примерить на выбранный день.

const SHOWN = 5;

function when(n: NewsIncident): string {
  const day = shortDate(n.start.slice(0, 10));
  return `${day}, ${n.start.slice(11, 16)}-${n.end ? n.end.slice(11, 16) : 'сейчас'}`;
}

export function NewsEvents() {
  const { data: feed, isLoading, error } = useNewsFeed();
  const date = useStore((s) => isoDate(dayIndex(s.minute)));
  const events = useStore((s) => s.scenario.events);
  const addEvent = useStore((s) => s.addEvent);
  const [all, setAll] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const inHorizon = date >= HORIZON_START && date <= HORIZON_END;

  const tryOn = async (n: NewsIncident) => {
    setBusy(n.id);
    setMessage(null);
    try {
      const res = await fetch(`/api/v1/news/${encodeURIComponent(n.id)}/events?date=${date}`);
      const body = (await res.json()) as ScenarioEvent[] | { detail?: string };
      if (!res.ok || !Array.isArray(body)) throw new Error(Array.isArray(body) ? `сервис ответил ${res.status}` : body.detail);
      if (events.length + body.length > MAX_EVENTS) {
        setMessage(`В сценарии уже ${events.length} событий, этот сбой добавит ещё ${body.length}; предел ${MAX_EVENTS}.`);
        return;
      }
      body.forEach(addEvent);
      setMessage(`Добавлено ${body.length} ${body.length === 1 ? 'событие' : body.length < 5 ? 'события' : 'событий'}: `
        + `такой же сбой ${shortDate(date)}. Итог по сети - в карточке выше.`);
    } catch (e) {
      setMessage(`Не удалось примерить сбой: ${e instanceof Error ? e.message : 'ошибка сети'}`);
    } finally {
      setBusy(null);
    }
  };

  if (isLoading) return <TramDots label="Читаем новости Дептранса" />;
  if (error || !feed) return <p className={styles.note}>Лента сбоев недоступна: сервис не ответил.</p>;
  const live = feed.incidents.filter((n) => n.origin === 'live');
  const list = feed.incidents.slice(0, all ? feed.incidents.length : SHOWN);

  return (
    <section className={styles.group}>
      <h3 className={styles.groupTitle}>Сбои из новостей Дептранса
        <InfoTip>Сервис читает канал t.me/DtOperativno: сообщение «задерживаются трамваи №…» и ответ «движение
          восстановлено» дают сбой с началом и концом. В часы сбоя посадки маршрута умножаются на 1 - {fmt1(feed.alpha)} ×
          долю часа под сбоем: за полный час остановки маршрут теряет около половины посадок. Оценка по сбоям 2025 года,
          {' '}{feed.alphaSource.replace(/^analysis\/\S+: /, '')}. Сбои ноября-декабря уже учтены в прогнозе v11.</InfoTip>
      </h3>
      <p className={styles.note}>
        {feed.liveCheckedAt
          ? `Канал проверен в ${new Date(feed.liveCheckedAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}`
            + (feed.liveError ? `: ${feed.liveError}. ` : ': ')
            + (live.length ? `свежих сбоев трамваев ${live.length}.` : 'свежих сбоев на десяти маршрутах нет.')
          : 'Живая лента выключена, показан архив 2025 года.'}
        {' '}{inHorizon ? `«Примерить» переносит такой же сбой на ${shortDate(date)}.`
          : 'Чтобы примерить сбой, выберите день в ноябре-декабре 2025.'}
      </p>
      {list.map((n) => (
        <div key={n.id} className={styles.news}>
          <div className={styles.newsHead}>
            {n.routes.map((r) => <b key={r} className={styles.newsRoute} style={{ color: routeColor(r) }}>№{r}</b>)}
            <span>{when(n)}{n.minutes != null ? `, ${Math.round(n.minutes)} мин` : ''}</span>
            {n.origin === 'live' && <em className={styles.newsLive}>{n.end ? 'свежий' : 'идёт сейчас'}</em>}
            {n.inForecast && <em className={styles.newsIn} title="День сбоя в горизонте: сбой уже учтён в прогнозе по умолчанию">
              в прогнозе</em>}
          </div>
          <small title={n.location}>{n.causeLabel}. {n.location}</small>
          <div className={styles.row}>
            <button type="button" className={styles.btn} disabled={!inHorizon || !n.end || busy != null}
              onClick={() => void tryOn(n)}
              title={!n.end ? 'Движение ещё не восстановлено: длительность неизвестна' : undefined}>
              {busy === n.id ? 'Считаем…' : `Примерить на ${shortDate(date)}`}
            </button>
            <a href={n.sourceUrl} target="_blank" rel="noopener noreferrer" className={styles.newsLink}>
              сообщение <Icon.external /></a>
          </div>
        </div>
      ))}
      {feed.incidents.length > SHOWN && (
        <button type="button" className={styles.btn} onClick={() => setAll((v) => !v)}>
          {all ? 'Свернуть' : `Все сбои: ${feed.incidents.length}`}</button>
      )}
      {message && <p className={styles.note} role="status">{message}</p>}
    </section>
  );
}
