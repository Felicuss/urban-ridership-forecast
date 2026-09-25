import { useMemo, useState } from 'react';
import { useCalendar, useFactors, useNetworkLoad, useSeries, type SeriesQuery } from '../../api/queries';
import type { Factors, Horizon, Series } from '../../api/types';
import { useStore } from '../../state/store';
import { MINUTES_PER_DAY, dayIndex, dayOf, hourOf, isoDate, monthLabel, shortDate } from '../../lib/time';
import { fmtCompact, fmtInt, fmtPct, fmtRange } from '../../lib/format';
import { targetQuery, useTarget } from '../../hooks/useTarget';
import { headway } from '../map/trams';
import { BandChart, type BandSeries } from '../charts/BandChart';
import { Card, InfoTip, Kpi, Segmented, TramDots } from '../ui/Controls';
import styles from './Panels.module.css';

const SOURCE_LABEL: Record<string, string> = { fact: 'факт', forecast: 'прогноз', outlook: 'оценка' };

/** У факта нижняя и верхняя граница совпадают: вместо «коридор 242-242» пишем, что это факт. */
function band(p10: number, p90: number): string {
  return Math.round(p10) === Math.round(p90) ? 'факт, коридора нет' : `коридор ${fmtRange(p10, p90)}`;
}

const HORIZONS: { value: Horizon; label: string; hint: string }[] = [
  { value: 'day', label: 'Сутки', hint: 'По часам выбранного дня' },
  { value: 'month', label: 'Месяц', hint: 'По дням месяца' },
  { value: 'year', label: 'Год', hint: 'По месяцам: ноябрь 2025 - октябрь 2026' },
];

const UNIT: Record<Horizon, { total: string; peak: string; now: string }> = {
  day: { total: 'Посадок за сутки', peak: 'Пиковый час', now: 'В выбранный час' },
  month: { total: 'Посадок за месяц', peak: 'Пиковый день', now: 'В выбранный день' },
  year: { total: 'Посадок за 12 месяцев', peak: 'Пиковый месяц', now: 'Ноябрь 2025' },
};

function label(period: string, horizon: Horizon): string {
  if (horizon === 'day') return period.slice(11, 13);
  if (horizon === 'month') return shortDate(period);
  return monthLabel(period).slice(0, 3);
}

/** Факт тех же месяцев 2025 года из данных организаторов: для горизонта «год» у маршрута и сети. */
function history2025(factors: Factors | undefined, series: Series, route: number | null, level: string) {
  if (!factors || series.granularity !== 'month' || level === 'stop') return undefined;
  const routes = route != null ? [String(route)] : Object.keys(factors.history.routes);
  const byMonth = new Map<string, number>();
  factors.history.dates.forEach((d, i) => {
    const m = d.slice(5, 7);
    const v = routes.reduce((a, r) => a + (factors.history.routes[r]?.[i] ?? 0), 0);
    byMonth.set(m, (byMonth.get(m) ?? 0) + v);
  });
  return series.points.map((p) => (p.period.startsWith('2026') ? byMonth.get(p.period.slice(5, 7)) ?? null : null));
}

export function ForecastTab() {
  const horizon = useStore((s) => s.horizon);
  const setHorizon = useStore((s) => s.setHorizon);
  const day = useStore((s) => dayIndex(s.minute));
  const hour = useStore((s) => hourOf(s.minute));
  const setMinute = useStore((s) => s.setMinute);
  const scenario = useStore((s) => s.scenario);
  const target = useTarget();
  const factors = useFactors().data;
  const calendar = useCalendar().data;
  const load = useNetworkLoad(isoDate(day), scenario).data;
  const query = useMemo<SeriesQuery>(() => {
    const base = targetQuery(target);
    if (horizon === 'day') return { ...base, horizon: 'day', from: isoDate(day) };
    if (horizon === 'month') return { ...base, horizon: 'month', from: isoDate(day) };
    return { ...base, horizon: 'year' };
  }, [target, horizon, day]);
  const { data: series, isFetching } = useSeries(query, scenario);

  const chart = useMemo<BandSeries | null>(() => {
    if (!series) return null;
    return {
      labels: series.points.map((p) => label(p.period, horizon)),
      p50: series.points.map((p) => p.p50),
      p10: series.points.map((p) => p.p10),
      p90: series.points.map((p) => p.p90),
      baseline: series.scenario ? series.points.map((p) => p.baseline ?? null) : undefined,
      history: history2025(factors, series, target.route, target.level),
    };
  }, [series, horizon, factors, target.route, target.level]);

  if (!series || !chart) return <TramDots label="Считаем прогноз" />;

  const cursor = horizon === 'day' ? hour : horizon === 'month'
    ? series.points.findIndex((p) => p.period === isoDate(day)) : series.points.findIndex((p) => p.period === isoDate(day).slice(0, 7));
  const peak = series.points.reduce((a, p) => (p.p50 > a.p50 ? p : a), series.points[0]!);
  const current = series.points[cursor] ?? series.points[0]!;
  const spread = series.total.p50 > 0 ? (100 * (series.total.p90 - series.total.p10)) / 2 / series.total.p50 : 0;
  const delta = series.scenario && series.total.baseline
    ? (100 * (series.total.p50 - series.total.baseline)) / series.total.baseline : null;

  return (
    <div className={styles.stack}>
      <div className={styles.targetHead}>
        <span className={styles.targetDot} style={{ background: target.color }} />
        <div>
          <h2>{target.name}{series.target.estimate && <em className={styles.estimate}>по долям остановок</em>}
            <em className={`${styles.source} ${styles[current.source]}`}>{SOURCE_LABEL[current.source]}</em></h2>
          <p>{target.subtitle}</p>
        </div>
        {isFetching && <span className={styles.spinner} aria-label="Обновляем" />}
      </div>
      <Segmented value={horizon} options={HORIZONS} onChange={setHorizon} label="Горизонт прогноза" />
      <div className={styles.kpis}>
        <Kpi label={UNIT[horizon].total} value={fmtCompact(series.total.p50)}
          sub={band(series.total.p10, series.total.p90)}
          info="Прогноз и коридор: на проверке по прошлым месяцам факт попадал в коридор в 8 случаях из 10. Коридор за сутки или месяц складывается из коридоров часов, поэтому он шире реального." />
        <Kpi label={UNIT[horizon].peak} value={fmtCompact(peak.p50)}
          sub={horizon === 'day' ? `${peak.period.slice(11, 13)}:00-${Number(peak.period.slice(11, 13)) + 1}:00`
            : horizon === 'month' ? shortDate(peak.period) : monthLabel(peak.period)} tone="accent" />
        <Kpi label={UNIT[horizon].now} value={fmtInt(current.p50)}
          sub={band(current.p10, current.p90)} />
        {delta != null ? (
          <Kpi label="Сценарий к базе" value={fmtPct(delta)} tone={delta >= 0 ? 'up' : 'down'}
            sub={`база ${fmtCompact(series.total.baseline)}`}
            info="Разница между прогнозом с изменёнными ползунками и прогнозом по умолчанию за тот же период." />
        ) : current.source === 'fact' ? (
          <Kpi label="Источник" value="факт" sub="валидации, коридора нет"
            info="Январь-октябрь 2025: успешные валидации из данных организаторов, это не прогноз." />
        ) : (
          <Kpi label="Неопределённость" value={`±${Math.round(spread)} %`} sub="полширины коридора к прогнозу"
            info="Чем шире коридор, тем меньше уверенность. Для года коридор ±12 %: сезонный индекс ошибался до 12,6 % на реальных месяцах." />
        )}
      </div>
      <Card title={horizon === 'day' ? 'Посадки по часам' : horizon === 'month' ? 'Посадки по дням' : 'Посадки по месяцам'}
        info="Линия - прогноз, заливка - коридор, куда факт попадает в 8 случаях из 10. Пунктир - прогноз по умолчанию, когда включён сценарий. Серым на годе - факт тех же месяцев 2025 года. Клик по графику переносит время.">
        <BandChart data={chart} color={target.color} cursorIndex={cursor >= 0 ? cursor : undefined} height={190}
          onPick={(i) => {
            if (horizon === 'day') setMinute(day * MINUTES_PER_DAY + i * 60 + 30);
            if (horizon === 'month') {
              const p = series.points[i];
              if (p) setMinute(dayOf(p.period) * MINUTES_PER_DAY + hour * 60);
            }
          }} />
      </Card>
      {horizon === 'day' && target.route != null && <PerTrip route={target.route} load={load?.routes.get(target.route)}
        factors={factors} dayOff={calendar?.[day]?.dayOff ?? false} hour={hour} />}
      {series.notes.map((n) => <p key={n} className={styles.note}>{n}</p>)}
    </div>
  );
}

/** Посадки на один рейс по часам: где вагонов не хватает относительно спроса. */
function PerTrip({ route, load, factors, dayOff, hour }: {
  route: number;
  load: number[] | undefined;
  factors: Factors | undefined;
  dayOff: boolean;
  hour: number;
}) {
  const perTrip = Array.from({ length: 24 }, (_, h) => {
    const hw = headway(factors, route, dayOff, h);
    return hw && load ? (load[h] ?? 0) / (2 * (60 / hw)) : 0;
  });
  const [limit, setLimit] = useState(CAPACITY);
  const max = Math.max(...perTrip, limit, 1);
  const peakHour = perTrip.indexOf(Math.max(...perTrip));
  return (
    <Card title="Посадок на рейс" info="Посадки маршрута в час ÷ рейсы в обе стороны по расписанию transport.mos.ru. Высокие столбики - часы, где на один вагон приходится больше всего входящих: кандидаты на дополнительные выпуски.">
      <div className={styles.bars} role="img" aria-label="Посадок на рейс по часам">
        {perTrip.map((v, h) => (
          <span key={h} className={h === hour ? styles.barOn : styles.bar} title={`${h}:00 - ${fmtInt(v)} на рейс`}
            style={{ height: `${Math.max((v / max) * 100, v > 0 ? 3 : 0)}%`,
              background: v > limit ? 'var(--red)' : v > 0.8 * limit ? 'var(--warn)' : undefined }} />
        ))}
      </div>
      <div className={styles.barsAxis}><span>0</span><span>6</span><span>12</span><span>18</span><span>23</span></div>
      <p className={styles.note}>
        Больше всего на рейс в {peakHour}:00, около {fmtInt(perTrip[peakHour])} посадок.
        <InfoTip>Это поток входящих за рейс, а не наполнение: выходы в данных не видны. «Витязь-М» везёт 185 человек при 5 чел/м² и 260 при 8 чел/м² (данные производителя, pk-ts.org).</InfoTip>
      </p>
      <div className={styles.coefHead}>
        <span>Порог посадок на рейс
          <InfoTip>Выше порога столбик красный, и ниже появляется совет добавить рейсы. По умолчанию порог равен
            вместимости вагона при 5 чел/м²: если за рейс входит больше людей, чем помещается в вагон, стоит проверить
            наполнение на загруженном участке.</InfoTip></span>
        <span className={styles.coefValue}>{limit}</span>
      </div>
      <input className={styles.range} type="range" min={100} max={300} step={5} value={limit}
        aria-label="Порог посадок на рейс" style={{ '--fill': `${((limit - 100) / 200) * 100}%` } as React.CSSProperties}
        onChange={(e) => setLimit(Number(e.target.value))} />
      <TripAdvice route={route} load={load} factors={factors} dayOff={dayOff} limit={limit} />
    </Card>
  );
}

/** Вместимость «Витязя-М» при 5 чел/м² - порог по умолчанию; ниже QUIET_LIMIT посадок рейс почти пустой. */
const CAPACITY = 185;
const QUIET_LIMIT = 15;

/** Чаще, чем раз в 3 минуты в каждую сторону, трамваи на линию не выпустить. */
const MIN_HEADWAY = 3;

interface HourAdvice {
  h: number;
  now: number;
  need: number;
}

interface HourRange {
  from: number;
  to: number;
  now: number;
  need: number;
}

/** Соседние часы склеиваются в один отрезок «7-10 ч»: берётся самый частый нужный интервал. */
function ranges(hours: HourAdvice[]): HourRange[] {
  return hours.reduce<HourRange[]>((acc, x) => {
    const last = acc[acc.length - 1];
    if (last && last.to === x.h) {
      return [...acc.slice(0, -1), { ...last, to: x.h + 1, now: Math.min(last.now, x.now), need: Math.min(last.need, x.need) }];
    }
    return [...acc, { from: x.h, to: x.h + 1, now: x.now, need: x.need }];
  }, []);
}

/** Вывод для диспетчера: в какие часы сократить интервал и где рейсы почти пустые. */
function TripAdvice({ route, load, factors, dayOff, limit }: {
  route: number;
  load: number[] | undefined;
  factors: Factors | undefined;
  dayOff: boolean;
  limit: number;
}) {
  if (!load) return null;
  const hours = Array.from({ length: 24 }, (_, h) => {
    const hw = headway(factors, route, dayOff, h) ?? 0;
    const boardings = load[h] ?? 0;
    const trips = hw ? 2 * (60 / hw) : 0;
    // рейсов в обе стороны, чтобы на каждый приходилось не больше порога, и интервал для них
    const need = boardings > 0 ? Math.floor(120 / Math.ceil(boardings / limit)) : hw;
    return { h, now: hw, need, trips, boardings };
  });
  const busy = ranges(hours.filter((x) => x.now > 0 && x.need < x.now));
  const quiet = ranges(hours.filter((x) => x.trips > 0 && x.h >= 6 && x.boardings / x.trips < QUIET_LIMIT));
  return (
    <ul className={styles.advice}>
      {busy.map((r) => (
        <li key={`b${r.from}`} className={styles.adviceUp}>
          <b>{r.from}-{r.to} ч:</b>{' '}
          {r.need >= MIN_HEADWAY
            ? `интервал ${r.need} мин вместо ${r.now}, чтобы на рейс приходилось не больше ${limit} посадок`
            : `даже интервал ${MIN_HEADWAY} мин не опустит поток ниже ${limit} посадок на рейс: нужны вагоны вместительнее или параллельный маршрут`}
        </li>
      ))}
      {busy.length === 0 && <li>Во все часы меньше {limit} посадок на рейс: интервалов по расписанию хватает.</li>}
      {quiet.map((r) => (
        <li key={`q${r.from}`} className={styles.adviceDown}>
          <b>{r.from}-{r.to} ч:</b> меньше {QUIET_LIMIT} посадок на рейс, интервал {r.now} мин можно увеличить
        </li>
      ))}
    </ul>
  );
}
