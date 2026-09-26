import { useMemo, useState } from 'react';
import { useCalendar, useFactors, useNetworkLoad } from '../../../api/queries';
import { useWeatherGrid } from '../../../hooks/useWeather';
import { useDaysLoad, useManyRouteStops } from '../../../hooks/useDispatch';
import { useNews, newsLine } from '../../../hooks/useNews';
import { useStore } from '../../../state/store';
import { buildBrief } from '../../../lib/brief';
import { CAPACITY, intervalAdvice } from '../../../lib/dispatch';
import { askFromUi } from '../../../lib/agent';
import { CENTER_INDEX } from '../../../lib/weatherGrid';
import { MINUTES_PER_DAY, dayIndex, isoDate, shortDate } from '../../../lib/time';
import { capitalize, fmtCompact, fmtInt, fmtPct } from '../../../lib/format';
import { ROUTE_IDS, routeColor } from '../../../lib/routes';
import { Card, Kpi, TramDots } from '../../ui/Controls';
import styles from './Shift.module.css';

/** Сводка смены на выбранный день: что сказать бригаде утром и что скопировать в рабочий чат. */
export function BriefCard() {
  const day = useStore((s) => dayIndex(s.minute));
  const scenario = useStore((s) => s.scenario);
  const setMinute = useStore((s) => s.setMinute);
  const selectRoute = useStore((s) => s.selectRoute);
  const date = isoDate(day);
  const load = useNetworkLoad(date, scenario).data;
  const weekAgo = useDaysLoad(day - 7, 1).days[0]?.load;
  const factors = useFactors().data;
  const calendar = useCalendar().data;
  const grid = useWeatherGrid(date).data;
  const stops = useManyRouteStops(ROUTE_IDS);
  const news = useNews().data;
  const [copied, setCopied] = useState<'ok' | 'fail' | null>(null);

  const brief = useMemo(() => {
    if (!load || load.date !== date) return null;
    const c = grid?.[CENTER_INDEX];
    return buildBrief({ day, calendar: calendar?.[day], load, weekAgo, factors, routes: ROUTE_IDS, limit: CAPACITY,
      weather: c ? { temp: c.temp, rain: c.rain, snow: c.snow } : null, scenarioEvents: scenario.events, stops,
      news: news?.filter((n) => n.start.slice(0, 10) === date).map(newsLine) });
  }, [load, date, grid, day, calendar, weekAgo, factors, scenario.events, stops, news]);

  if (!brief) return <TramDots label="Собираем сводку смены" />;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(brief.text);
      setCopied('ok');
    } catch {
      setCopied('fail');
    }
    setTimeout(() => setCopied(null), 2500);
  };

  return (
    <Card id="shift-brief" title={`Сводка смены: ${brief.title}`}
      info="Собирается из прогноза на день, расписания, погоды Open-Meteo и событий сети. Кнопка «Скопировать» кладёт текст в буфер обмена, чтобы отправить его в рабочий чат.">
      <p className={styles.meta}>
        {capitalize(brief.dayKind)}, {brief.source}{brief.weather ? `. Погода: ${brief.weather}` : ''}
      </p>
      <div className={styles.kpis3}>
        <Kpi label="Посадок" value={`${fmtInt(brief.total / 1000)} тыс.`} sub="за сутки" />
        <Kpi label="Пиковый час" value={`${brief.peakHour}:00`} sub={fmtCompact(brief.peak)} tone="accent" />
        <Kpi label="К неделе назад" value={brief.vsWeek != null ? fmtPct(brief.vsWeek) : '-'}
          tone={brief.vsWeek == null ? undefined : brief.vsWeek >= 0 ? 'up' : 'down'} sub={`к ${shortDate(isoDate(day - 7))}`} />
      </div>
      <p className={styles.line}>
        Больше всего посадок:{' '}
        {brief.top.map((r, i) => (
          <span key={r.route}>{i > 0 && ', '}<b style={{ color: routeColor(r.route) }}>№{r.route}</b> {fmtCompact(r.total)}</span>
        ))}
      </p>
      <div>
        <p className={styles.sub}>
          {brief.crowded.length ? `Тесно: больше ${CAPACITY} посадок на рейс` : `Тесных часов нет: везде меньше ${CAPACITY} посадок на рейс`}
        </p>
        <ul className={styles.rows}>
          {brief.crowded.slice(0, 4).map((c) => (
            <li key={`${c.route}-${c.from}`}>
              <button type="button" className={styles.rowBtn} title="Показать этот час и маршрут"
                onClick={() => { selectRoute(c.route); setMinute(day * MINUTES_PER_DAY + c.peakHour * 60 + 30); }}>
                <span className={styles.badge} style={{ '--c': routeColor(c.route) } as React.CSSProperties}>{c.route}</span>
                <span>{c.from}-{c.to} ч, до <b className="num">{fmtInt(c.peak)}</b> на рейс</span>
                <small>{intervalAdvice(c)}</small>
              </button>
            </li>
          ))}
        </ul>
      </div>
      {brief.events.length > 0 && (
        <div>
          <p className={styles.sub}>События дня</p>
          <ul className={styles.events}>{brief.events.map((e) => <li key={e}>{e}</li>)}</ul>
        </div>
      )}
      <div className={styles.actions}>
        <button type="button" className={styles.primary} onClick={() => void copy()}>
          {copied === 'ok' ? 'Скопировано' : copied === 'fail' ? 'Буфер обмена недоступен' : 'Скопировать для чата'}
        </button>
        <button type="button" className={styles.secondary} title="Помощник диспетчера перескажет сводку своими словами"
          onClick={() => askFromUi(`Составь короткую сводку смены на ${date}: пики, погода, события, где сократить интервал.`)}>
          Сводка от помощника
        </button>
      </div>
    </Card>
  );
}
