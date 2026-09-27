import { useMemo, useState } from 'react';
import { useCalendar, useFactors, useMeta, useNetworkLoad, useSeries, type SeriesQuery } from '../../api/queries';
import type { Factors, Horizon, Series } from '../../api/types';
import { useStore } from '../../state/store';
import { MINUTES_PER_DAY, dayIndex, dayOf, hourOf, isoDate, monthLabel, shortDate, weekStart, weekdayName } from '../../lib/time';
import { fmtCompact, fmtInt, fmtPct, fmtRange, plainDash } from '../../lib/format';
import { targetQuery, useTarget } from '../../hooks/useTarget';
import { CAPACITY, MIN_HEADWAY, headway } from '../../lib/dispatch';
import { BandChart, type BandSeries } from '../charts/BandChart';
import { Card, InfoTip, Kpi, Segmented, TramDots } from '../ui/Controls';
import { CompareBar, compareLabel, useCompareDay } from './CompareBar';
import { ExplainCard } from './ExplainCard';
import styles from './Panels.module.css';

const SOURCE_LABEL: Record<string, string> = { fact: 'факт', forecast: 'прогноз', outlook: 'оценка' };

/** У факта нижняя и верхняя граница совпадают: вместо «коридор 242–242» пишем, что это факт. */
function band(p10: number, p90: number): string {
  return Math.round(p10) === Math.round(p90) ? 'факт, коридора нет' : `коридор ${fmtRange(p10, p90)}`;
}

const HORIZONS: { value: Horizon; label: string; hint: string }[] = [
  { value: 'day', label: 'Сутки', hint: 'По часам выбранного дня' },
  { value: 'week', label: 'Неделя', hint: 'По дням с понедельника по воскресенье, у каждого дня пиковый час' },
  { value: 'month', label: 'Месяц', hint: 'По дням месяца, у каждого дня пиковый час' },
  { value: 'year', label: 'Год', hint: 'Календарный год выбранной даты, по месяцам' },
];

const UNIT: Record<Horizon, { total: string; peak: string; now: string }> = {
  day: { total: 'Посадок за сутки', peak: 'Пиковый час', now: 'В выбранный час' },
  week: { total: 'Посадок за неделю', peak: 'Пиковый час недели', now: 'В выбранный день' },
  month: { total: 'Посадок за месяц', peak: 'Пиковый час месяца', now: 'В выбранный день' },
  year: { total: 'Посадок за 12 месяцев', peak: 'Пиковый месяц', now: 'В выбранный месяц' },
};

function label(period: string, horizon: Horizon): string {
  if (horizon === 'day') return period.slice(11, 13);
  if (horizon === 'week') return `${weekdayName(dayOf(period), true)} ${shortDate(period)}`;
  if (horizon === 'month') return shortDate(period);
  return monthLabel(period).slice(0, 3);
}

/**
 * Восстановленные посадки в дни пропуска данных у маршрута: по часам для суток, суммой за день для недели
 * и месяца. Вне пропуска null, пунктира нет.
 */
function restoredLine(factors: Factors | undefined, series: Series, route: number | null, horizon: Horizon) {
  const days = route != null ? factors?.gaps?.restored[String(route)] : undefined;
  if (!days || horizon === 'year') return undefined;
  const line = series.points.map((p) => {
    if (horizon === 'day') return days[p.period.slice(0, 10)]?.[Number(p.period.slice(11, 13))] ?? null;
    const hours = days[p.period];
    return hours ? hours.reduce((a, b) => a + b, 0) : null;
  });
  return line.some((v) => v != null) ? line : undefined;
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
  return series.points.map((p) => (p.period.slice(0, 4) >= '2026' ? byMonth.get(p.period.slice(5, 7)) ?? null : null));
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
  const planQuality = useMeta().data?.quality.plan;
  const calendar = useCalendar().data;
  const load = useNetworkLoad(isoDate(day), scenario).data;
  const query = useMemo<SeriesQuery>(() => {
    const base = targetQuery(target);
    if (horizon === 'day') return { ...base, horizon: 'day', from: isoDate(day) };
    if (horizon === 'week') return { ...base, horizon: 'week', from: isoDate(weekStart(day)) };
    if (horizon === 'month') return { ...base, horizon: 'month', from: isoDate(day) };
    return { ...base, horizon: 'year', from: `${isoDate(day).slice(0, 4)}-01-01` };
  }, [target, horizon, day]);
  const { data: series, isFetching } = useSeries(query, scenario);
  const compareDay = useCompareDay(day, horizon);
  const compareQuery = useMemo<SeriesQuery | null>(() => (compareDay == null || horizon === 'year' ? null
    : { ...query, from: isoDate(horizon === 'week' ? weekStart(compareDay) : compareDay) }), [query, compareDay, horizon]);
  const other = useSeries(compareQuery, scenario).data;

  const restored = useMemo(() => (series && !series.scenario ? restoredLine(factors, series, target.route, horizon) : undefined),
    [series, factors, target.route, horizon]);
  const gap = target.route != null
    ? factors?.gaps?.periods.find((p) => p.route === target.route && p.from <= isoDate(day) && isoDate(day) <= p.to)
    : undefined;

  const chart = useMemo<BandSeries | null>(() => {
    if (!series) return null;
    return {
      labels: series.points.map((p) => label(p.period, horizon)),
      p50: series.points.map((p) => p.p50),
      p10: series.points.map((p) => p.p10),
      p90: series.points.map((p) => p.p90),
      baseline: series.scenario ? series.points.map((p) => p.baseline ?? null) : restored,
      baselineLabel: series.scenario ? 'база' : 'восстановлено',
      history: history2025(factors, series, target.route, target.level),
      compare: compareQuery && other ? series.points.map((_, i) => other.points[i]?.p50 ?? null) : undefined,
      compareLabel: compareDay != null ? compareLabel(compareDay, horizon) : undefined,
      plan: series.points.some((p) => p.plan != null) ? series.points.map((p) => p.plan ?? null) : undefined,
    };
  }, [series, horizon, factors, target.route, target.level, compareQuery, other, compareDay, restored]);

  if (!series || !chart) return <TramDots label="Считаем прогноз" />;

  const byDay = horizon === 'week' || horizon === 'month';
  const cursor = horizon === 'day' ? hour : byDay
    ? series.points.findIndex((p) => p.period === isoDate(day)) : series.points.findIndex((p) => p.period === isoDate(day).slice(0, 7));
  const peak = series.points.reduce((a, p) => (p.p50 > a.p50 ? p : a), series.points[0]!);
  const peakHour = byDay ? series.total : null;
  const current = series.points[cursor] ?? series.points[0]!;
  const spread = series.total.p50 > 0 ? (100 * (series.total.p90 - series.total.p10)) / 2 / series.total.p50 : 0;
  const delta = series.scenario && series.total.baseline
    ? (100 * (series.total.p50 - series.total.baseline)) / series.total.baseline : null;
  const plan = series.total.plan;
  const vsPlan = plan ? (100 * (series.total.p50 - plan)) / plan : null;

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
        {peakHour?.peak != null && peakHour.peakAt ? (
          <Kpi label={UNIT[horizon].peak} value={fmtInt(peakHour.peak)} sub={peakLabel(peakHour.peakAt)} tone="accent"
            info="Самый загруженный час за период и посадки в нём по всему объекту." />
        ) : (
          <Kpi label={UNIT[horizon].peak} value={fmtCompact(peak.p50)}
            sub={horizon === 'day' ? `${peak.period.slice(11, 13)}:00–${Number(peak.period.slice(11, 13)) + 1}:00`
              : monthLabel(peak.period)} tone="accent" />
        )}
        <Kpi label={horizon === 'year' ? monthLabel(current.period) : UNIT[horizon].now} value={fmtInt(current.p50)}
          sub={band(current.p10, current.p90)} />
        {delta != null ? (
          <Kpi label="Сценарий к базе" value={fmtPct(delta)} tone={delta >= 0 ? 'up' : 'down'}
            sub={`база ${fmtCompact(series.total.baseline)}`}
            info="Разница между прогнозом с изменёнными ползунками и прогнозом по умолчанию за тот же период." />
        ) : vsPlan != null && plan != null ? (
          <Kpi label="Факт к плану" value={fmtPct(vsPlan)} tone={vsPlan >= 0 ? 'up' : 'down'} sub={`план ${fmtCompact(plan)}`}
            info={`План - прогноз, который модель сделала бы вечером накануне: профиль за 2 недели по данным до этого дня.${
              planQuality ? ` За февраль-октябрь 2025 его точность против факта ${fmt3(planQuality.wape_score_hour)} по часам и ${
                fmt3(planQuality.wape_score_day)} по суткам маршрута.` : ''}`} />
        ) : current.source === 'fact' ? (
          <Kpi label="Источник" value="факт" sub="валидации, коридора нет"
            info="Январь-октябрь 2025: успешные валидации из данных организаторов, это не прогноз." />
        ) : (
          <Kpi label="Разброс прогноза" value={`±${Math.round(spread)} %`} sub="половина коридора"
            info="Чем шире коридор, тем меньше уверенность. Для года коридор ±12 %: сезонный индекс ошибался до 12,6 % на реальных месяцах." />
        )}
      </div>
      <Card title={horizon === 'day' ? 'Посадки по часам' : byDay ? 'Посадки по дням' : 'Посадки по месяцам'}
        info="Линия - прогноз, заливка - коридор, куда факт попадает в 8 случаях из 10. Белый пунктир - прогноз по умолчанию, когда включён сценарий. Жёлтые точки - другая дата из «Сравнить с». Серым на годе - факт тех же месяцев 2025 года. Голубой пунктир на прошедших днях - план: прогноз, сделанный накануне. Клик по графику переносит время.">
        <BandChart data={chart} color={target.color} cursorIndex={cursor >= 0 ? cursor : undefined} height={190}
          onPick={(i) => {
            if (horizon === 'day') setMinute(day * MINUTES_PER_DAY + i * 60 + 30);
            if (byDay) {
              const p = series.points[i];
              if (p) setMinute(dayOf(p.period) * MINUTES_PER_DAY + hour * 60);
            }
          }} />
      </Card>
      {gap && (
        <p className={styles.gapNote}>
          <b>Пропуск в данных {shortDate(gap.from)}{gap.to !== gap.from ? `-${shortDate(gap.to)}` : ''}:</b> {plainDash(gap.reason)}.
          {gap.source && <>{' '}<a href={gap.source} target="_blank" rel="noopener noreferrer">Источник</a>.</>}
          {' '}Белый пунктир - посадки, восстановленные по прошлым неделям: {fmtInt(gap.restored)} за период при факте {fmtInt(gap.fact)}.
        </p>
      )}
      {horizon === 'day' && (target.level === 'route' || target.level === 'network') && inHourlyForecast(isoDate(day)) && (
        <ExplainCard route={target.level === 'route' ? target.route ?? null : null} date={isoDate(day)} title={target.name} />
      )}
      <CompareBar day={day} horizon={horizon} series={series} other={compareQuery ? other : undefined} />
      {byDay && <PeakDays points={series.points} horizon={horizon} day={day}
        onPick={(d, h) => setMinute(d * MINUTES_PER_DAY + h * 60 + 30)} />}
      {horizon === 'day' && target.route != null && <PerTrip route={target.route} load={load?.routes.get(target.route)}
        factors={factors} dayOff={calendar?.[day]?.dayOff ?? false} hour={hour} />}
      {series.notes.map((n) => <p key={n} className={styles.note}>{n}</p>)}
    </div>
  );
}

/** Почасовой прогноз модели есть на 1 ноября - 31 декабря 2025: разбор по шагам формулы только для этих дат. */
function inHourlyForecast(date: string): boolean {
  return date >= '2025-11-01' && date <= '2025-12-31';
}

/** Точность с тремя знаками и десятичной запятой: 0.8912 -> «0,891». */
function fmt3(v: number): string {
  return v.toFixed(3).replace('.', ',');
}

/** «пт 14.11, 8:00–9:00» по метке часа 2025-11-14T08:00. */
function peakLabel(at: string): string {
  const h = Number(at.slice(11, 13));
  return `${weekdayName(dayOf(at.slice(0, 10)), true)} ${shortDate(at.slice(0, 10))}, ${h}:00–${h + 1}:00`;
}

/** Сколько самых напряжённых дней месяца показывать списком. */
const TOP_DAYS = 7;

/**
 * Пики по дням: в каждом дне недели или месяца самый загруженный час и посадки в него. Для месяца - семь
 * самых напряжённых дней. Клик по строке переносит время на этот час.
 */
function PeakDays({ points, horizon, day, onPick }: {
  points: Series['points'];
  horizon: Horizon;
  day: number;
  onPick: (day: number, hour: number) => void;
}) {
  const withPeak = points.filter((p) => p.peak != null && p.peakAt);
  const rows = horizon === 'month' ? [...withPeak].sort((a, b) => (b.peak ?? 0) - (a.peak ?? 0)).slice(0, TOP_DAYS) : withPeak;
  const max = Math.max(...rows.map((p) => p.peak ?? 0), 1);
  if (!rows.length) return null;
  return (
    <Card title={horizon === 'month' ? 'Самые напряжённые дни месяца' : 'Пики нагрузки по дням'}
      info="Для каждого дня - час с наибольшим числом посадок, посадки в этот час и справа посадки за сутки. По сумме за сутки пик не виден: у дня с меньшей суммой утренний час бывает загруженнее.">
      <ul className={styles.peaks}>
        {rows.map((p) => {
          const d = dayOf(p.period);
          const h = Number((p.peakAt ?? '').slice(11, 13));
          const top = p.peak === max;
          return (
            <li key={p.period}>
              <button type="button" className={d === day ? styles.peakRowOn : styles.peakRow} onClick={() => onPick(d, h)}
                title="Перейти к этому часу">
                <span className={styles.peakDay}>{weekdayName(d, true)} {shortDate(p.period)}</span>
                <span className={styles.peakHour}>{h}:00</span>
                <span className={styles.peakBar}><i style={{ width: `${(100 * (p.peak ?? 0)) / max}%` }} className={top ? styles.peakTop : undefined} /></span>
                <b className="num">{fmtInt(p.peak ?? 0)}</b>
                <small className="num" title="Посадок за сутки">{fmtCompact(p.p50)}</small>
              </button>
            </li>
          );
        })}
      </ul>
    </Card>
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
    <Card title={`Посадок на рейс: маршрут ${route}`} info="Посадки маршрута в час ÷ рейсы в обе стороны по расписанию transport.mos.ru. Высокие столбики - часы, где на один вагон приходится больше всего входящих: кандидаты на дополнительные выпуски.">
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
        <InfoTip>Считаются только вошедшие за рейс: выходов в данных нет. «Витязь-М» везёт 185 человек при 5 чел/м² и 260 при 8 чел/м² (данные производителя, pk-ts.org).</InfoTip>
      </p>
      <div className={styles.coefHead}>
        <span>Порог посадок на рейс
          <InfoTip>Выше порога столбик красный, а ниже карточки появляется совет, до какого интервала сократить движение. По умолчанию порог равен
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

/** Ниже QUIET_LIMIT посадок на рейс вагон почти пустой. */
const QUIET_LIMIT = 15;

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
