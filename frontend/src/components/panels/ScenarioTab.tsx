import { useMemo, useState } from 'react';
import { useCoefficients, useMeta, useSeries } from '../../api/queries';
import type { Coefficient, CoefficientValue, ScenarioEvent } from '../../api/types';
import { useShownRoutes, useStore } from '../../state/store';
import { HORIZON_END, HORIZON_START, TIMELINE_END, dayIndex, fullDate, isoDate, shortDate } from '../../lib/time';
import { fmtCompact, fmtFixed, fmtPct } from '../../lib/format';
import { Card, InfoTip, Kpi, Toggle, TramDots } from '../ui/Controls';
import { Icon } from '../ui/Icons';
import { NewsEvents } from './NewsEvents';
import styles from './Panels.module.css';

const GROUP_TITLES: Record<string, string> = {
  level: 'Уровень спроса',
  calendar: 'Календарь',
  events: 'События сети',
  weather: 'Погода',
};

const PRESETS: { label: string; make: (day: string) => ScenarioEvent }[] = [
  { label: 'Перекрытие маршрута 17 днём', make: (d) => ({ route: 17, from: d, to: d, hours: '10-17', multiplier: 0, label: 'перекрытие' }) },
  { label: 'Мероприятие: +30 % вечером', make: (d) => ({ from: d, to: d, hours: '17-21', multiplier: 1.3, label: 'массовое мероприятие' }) },
  { label: 'Снегопад: −15 % весь день', make: (d) => ({ from: d, to: d, multiplier: 0.85, label: 'снегопад' }) },
];

export default function ScenarioTab() {
  const catalog = useCoefficients().data;
  const score = useMeta().data?.leaderboardWapeScore;
  const scenario = useStore((s) => s.scenario);
  const setCoefficient = useStore((s) => s.setCoefficient);
  const resetScenario = useStore((s) => s.resetScenario);
  const groups = useMemo(() => {
    const map = new Map<string, Coefficient[]>();
    catalog?.forEach((c) => map.set(c.group, [...(map.get(c.group) ?? []), c]));
    return [...map.entries()];
  }, [catalog]);
  if (!catalog) return <TramDots label="Загружаем ползунки" />;

  return (
    <div className={styles.stack}>
      <p className={styles.note}>
        «Что если»: добавьте перекрытие, мероприятие или сбой из новостей, либо сдвиньте ползунок модели.
        События действуют на любой день с 1 ноября 2025 по 31 декабря 2027, ползунки модели - на ноябрь-декабрь
        2025. Факт прошедших дней не меняется.
      </p>
      <Impact />
      <Events />
      <NewsEvents />
      <h3 className={styles.groupTitle}>Коэффициенты модели
        <InfoTip>Со значениями по умолчанию это прогноз v25{score != null ? `, предполагаемая оценка на платформе ${fmtFixed(score, 5)}` : ''}. Ползунок
          сдвигает его: например, спрос в ноябре к октябрю или доля воскресенья в праздник.</InfoTip></h3>
      {groups.map(([group, items]) => (
        <section key={group} className={styles.group}>
          <h3 className={styles.groupTitle}>{GROUP_TITLES[group] ?? group}</h3>
          {items.map((c) => (
            <CoefficientRow key={c.key} c={c} value={scenario.coefficients[c.key]}
              onChange={(v) => setCoefficient(c.key, v === c.defaultValue ? undefined : v)} />
          ))}
        </section>
      ))}
      {(Object.keys(scenario.coefficients).length > 0 || scenario.events.length > 0) && (
        <button type="button" className={styles.btn} onClick={resetScenario}><Icon.reset />Вернуть значения по умолчанию</button>
      )}
    </div>
  );
}

function CoefficientRow({ c, value, onChange }: {
  c: Coefficient;
  value: CoefficientValue | undefined;
  onChange: (v: CoefficientValue) => void;
}) {
  const v = value ?? c.defaultValue;
  const changed = value !== undefined;
  const shown = typeof v === 'number' ? (Number.isInteger(c.step ?? 1) && c.type === 'integer' ? String(v)
    : fmtFixed(v, Math.max(0, Math.min(4, -Math.floor(Math.log10(c.step ?? 0.01))))))
    : typeof v === 'string' && /^\d{4}-\d{2}-\d{2}/.test(v) ? `${fullDate(v)}${v.length > 10 ? ` ${v.slice(11, 16)}` : ''}`
      : String(v);
  const head = (
    <div className={styles.coefHead}>
      <span className={styles.coefLabel}>{c.label}<InfoTip>{c.source}</InfoTip></span>
      <span className={styles.coefValue}>
        {c.type !== 'boolean' && shown}
        {changed && <button type="button" className={styles.reset} aria-label="Вернуть значение по умолчанию"
          onClick={() => onChange(c.defaultValue)}><Icon.reset /></button>}
      </span>
    </div>
  );
  if (c.type === 'boolean') {
    return (
      <div className={changed ? `${styles.coef} ${styles.coefChanged}` : styles.coef}>
        <Toggle checked={Boolean(v)} onChange={onChange} label={c.label} hint={c.source} />
      </div>
    );
  }
  if (c.type === 'date' || c.type === 'datetime') {
    return (
      <div className={changed ? `${styles.coef} ${styles.coefChanged}` : styles.coef}>
        {head}
        <input className={styles.input} type={c.type === 'date' ? 'date' : 'datetime-local'} value={String(v)}
          min={String(c.min ?? '')} max={String(c.max ?? '')} onChange={(e) => e.target.value && onChange(e.target.value)} />
      </div>
    );
  }
  const min = Number(c.min ?? 0);
  const max = Number(c.max ?? 1);
  const fill = `${(100 * (Number(v) - min)) / (max - min || 1)}%`;
  return (
    <div className={changed ? `${styles.coef} ${styles.coefChanged}` : styles.coef}>
      {head}
      <input className={styles.range} type="range" min={min} max={max} step={c.step ?? 0.01} value={Number(v)}
        aria-label={c.label} style={{ '--fill': fill } as React.CSSProperties}
        onChange={(e) => onChange(c.type === 'integer' ? Math.round(Number(e.target.value)) : Number(e.target.value))} />
    </div>
  );
}

/** Итог сценария по сети за весь горизонт: общая разница и разница по дням. */
function Impact() {
  const scenario = useStore((s) => s.scenario);
  const active = Object.keys(scenario.coefficients).length > 0 || scenario.events.length > 0;
  // период итога: горизонт прогноза, если тронуты ползунки, и даты событий, если их примерили на 2026 год
  const sliders = Object.keys(scenario.coefficients).length > 0;
  const first = scenario.events.reduce((m, e) => (e.from < m ? e.from : m), sliders ? HORIZON_START : TIMELINE_END);
  const last = scenario.events.reduce((m, e) => (e.to > m ? e.to : m), sliders ? HORIZON_END : HORIZON_START);
  const query = useMemo(() => ({ level: 'network' as const, from: first, to: last, granularity: 'day' as const }),
    [first, last]);
  const { data, isFetching } = useSeries(active ? query : null, scenario);
  if (!active) {
    return (
      <p className={styles.note}>Здесь появится разница с прогнозом по умолчанию по сети и по дням, а графики прогноза
        покажут базу пунктиром.</p>
    );
  }
  if (!data) return <TramDots label="Пересчитываем сценарий" />;
  const base = data.total.baseline ?? data.total.p50;
  const delta = base > 0 ? (100 * (data.total.p50 - base)) / base : 0;
  const deltas = data.points.map((p) => p.p50 - (p.baseline ?? p.p50));
  const max = Math.max(...deltas.map(Math.abs), 1);
  return (
    <Card title="Итог сценария по сети" actions={isFetching ? <TramDots label="" /> : undefined}
      info={`Сумма посадок всех маршрутов ${first === last ? `за ${shortDate(first)}` : `с ${shortDate(first)} по ${shortDate(last)}`}: сценарий против прогноза по умолчанию. Ползунки считаются за ноябрь-декабрь 2025, события - за свои дни. Столбики - разница по дням, вверх - больше посадок.`}>
      <div className={styles.split}>
        <Kpi label="За период" value={fmtPct(delta)} tone={delta >= 0 ? 'up' : 'down'}
          sub={`${fmtCompact(data.total.p50)} против ${fmtCompact(base)}`} />
        <Kpi label="Самый затронутый день" value={fmtSigned(deltas[deltas.map(Math.abs).indexOf(max)] ?? 0)}
          sub={shortDate(data.points[deltas.map(Math.abs).indexOf(max)]?.period ?? HORIZON_START)} />
      </div>
      <div className={styles.deltaBars} role="img" aria-label="Разница сценария по дням">
        {deltas.map((d, i) => (
          <span key={i} title={`${data.points[i]?.period}: ${fmtCompact(d)}`} style={{
            height: `${Math.max((Math.abs(d) / max) * 100, d !== 0 ? 4 : 1)}%`,
            background: d > 0 ? 'var(--ok)' : d < 0 ? 'var(--red)' : 'var(--surface-3)' }} />
        ))}
      </div>
    </Card>
  );
}

function Events() {
  const events = useStore((s) => s.scenario.events);
  const addEvent = useStore((s) => s.addEvent);
  const removeEvent = useStore((s) => s.removeEvent);
  const day = useStore((s) => isoDate(dayIndex(s.minute)));
  const shown = useShownRoutes();
  // даты формы следуют за выбранным днём, пока их не поменяли руками
  const [draft, setDraft] = useState<Omit<ScenarioEvent, 'from' | 'to'> & { from?: string; to?: string }>(
    { multiplier: 1, label: '' });
  const set = (patch: Partial<ScenarioEvent>) => setDraft((d) => ({ ...d, ...patch }));
  const canTry = day >= HORIZON_START && day <= TIMELINE_END;
  const from = draft.from ?? (canTry ? day : HORIZON_START);
  const to = draft.to ?? from;
  const ready = draft.multiplier !== 1 && from <= to;
  return (
    <section className={styles.group}>
      <h3 className={styles.groupTitle}>События: перекрытия, стройки, мероприятия
        <InfoTip>Событие умножает прогноз маршрута (или всех маршрутов) в выбранные дни и часы. 0 - перекрытие,
          1,3 - на 30 % больше пассажиров. Так в прогноз попадают события, о которых модель не знает.</InfoTip></h3>
      {events.map((e, i) => (
        <div key={`${e.from}-${i}`} className={styles.event}>
          <b>{e.label || 'событие'}: {e.route ? `маршрут ${e.route}` : 'все маршруты'} ×{fmtMultiplier(e.multiplier)}</b>
          <button type="button" className={styles.reset} aria-label="Удалить событие" onClick={() => removeEvent(i)}>
            <Icon.close /></button>
          <small>{e.from === e.to ? shortDate(e.from) : `${shortDate(e.from)} - ${shortDate(e.to)}`}, {hoursLabel(e.hours)}</small>
        </div>
      ))}
      <div className={styles.row}>
        {PRESETS.map((p) => (
          <button key={p.label} type="button" className={styles.btn} disabled={!canTry}
            title={canTry ? `Добавить на ${shortDate(day)}` : 'Выберите день с 1 ноября 2025: факт прошедших дней не меняется'}
            onClick={() => addEvent(p.make(day))}>{p.label}</button>
        ))}
      </div>
      {!canTry && <p className={styles.note}>Заготовки добавляют событие на выбранный день. Выберите день с 1 ноября 2025:
        факт прошедших дней сценарий не меняет.</p>}
      <div className={styles.coef}>
        <div className={styles.row}>
          <select className={styles.input} value={draft.route ?? ''} aria-label="Маршрут"
            onChange={(e) => set({ route: e.target.value ? Number(e.target.value) : undefined })}>
            <option value="">все маршруты</option>
            {shown.map((r) => <option key={r} value={r}>маршрут {r}</option>)}
          </select>
          <input className={styles.input} type="date" value={from} min={HORIZON_START} max={TIMELINE_END}
            aria-label="С даты" onChange={(e) => set({ from: e.target.value || undefined })} />
          <input className={styles.input} type="date" value={to} min={from} max={TIMELINE_END}
            aria-label="По дату" onChange={(e) => set({ to: e.target.value || undefined })} />
          <input className={styles.input} value={draft.hours ?? ''} placeholder="часы, 7-10" aria-label="Часы"
            style={{ width: 84 }} onChange={(e) => set({ hours: e.target.value || undefined })} />
        </div>
        <div className={styles.coefHead}>
          <span>Множитель</span><span className={styles.coefValue}>×{fmtFixed(draft.multiplier, 2)}</span>
        </div>
        <input className={styles.range} type="range" min={0} max={2} step={0.05} value={draft.multiplier}
          aria-label="Множитель события" style={{ '--fill': `${draft.multiplier * 50}%` } as React.CSSProperties}
          onChange={(e) => set({ multiplier: Number(e.target.value) })} />
        <div className={styles.row}>
          <input className={styles.input} value={draft.label ?? ''} placeholder="подпись" aria-label="Подпись события"
            style={{ flex: 1 }} onChange={(e) => set({ label: e.target.value })} />
          <button type="button" className={styles.btnPrimary} disabled={!ready}
            title={ready ? undefined : 'Сдвиньте множитель: при ×1 событие ничего не меняет'}
            onClick={() => addEvent({ ...draft, from, to, label: draft.label || 'событие' })}>Добавить</button>
        </div>
      </div>
    </section>
  );
}

/** Окно часов события на циферблате: «10-17» включает 17-й час, то есть 10:00-18:00. */
function hoursLabel(hours: string | undefined): string {
  if (!hours) return 'весь день';
  const [a, b] = hours.split('-').map(Number);
  const first = a ?? 0;
  const last = b ?? first;
  return `${first}:00–${last + 1}:00`;
}

function fmtSigned(v: number): string {
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${fmtCompact(Math.abs(v))}`;
}

function fmtMultiplier(m: number): string {
  return String(Math.round(m * 100) / 100).replace('.', ',');
}
