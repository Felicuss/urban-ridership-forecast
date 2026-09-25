import { useEffect, useState } from 'react';
import { download, useStops, type SeriesQuery } from '../../api/queries';
import { isDefaultScenario, useStore } from '../../state/store';
import { HORIZON_END, HORIZON_START, TIMELINE_END, TIMELINE_START, dayIndex, dayOf, isoDate, monthOf } from '../../lib/time';
import { fmtInt } from '../../lib/format';
import { targetQuery, useTarget } from '../../hooks/useTarget';
import { Segmented, Toggle } from '../ui/Controls';
import { Icon } from '../ui/Icons';
import sheet from './SettingsSheet.module.css';
import styles from './ExportSheet.module.css';

// Выгрузка прогноза с настройками: что выгружать, за какой период, с каким шагом и в каком формате.
// Число строк считается до запроса: лист Excel вмещает 1 048 575 строк, сервис откажет в большем.

type What = 'target' | 'routes' | 'stops' | 'network';
type Period = 'day' | 'month' | 'horizon' | 'year' | 'custom';
type Step = 'hour' | 'day' | 'month';

const MAX_ROWS = 1_048_575;
const ROUTES = 10;
const HOURS_PATTERN = /^(\d{1,2})-(\d{1,2})$/;

const PERIODS: { value: Period; label: string; hint: string }[] = [
  { value: 'day', label: 'Сутки', hint: 'Выбранный день' },
  { value: 'month', label: 'Месяц', hint: 'Месяц выбранного дня' },
  { value: 'horizon', label: 'Ноябрь-декабрь', hint: 'Горизонт прогноза из задания' },
  { value: 'year', label: 'Год', hint: 'Ноябрь 2025 - октябрь 2026 по месяцам' },
  { value: 'custom', label: 'Свой', hint: 'Любой интервал с января 2025 по октябрь 2026' },
];

const STEPS: { value: Step; label: string }[] = [
  { value: 'hour', label: 'По часам' },
  { value: 'day', label: 'По суткам' },
  { value: 'month', label: 'По месяцам' },
];

function range(period: Period, day: number, from: string, to: string): [string, string] {
  if (period === 'day') return [isoDate(day), isoDate(day)];
  if (period === 'month') {
    const m = monthOf(day);
    return [isoDate(m.first), isoDate(m.first + m.days - 1)];
  }
  if (period === 'horizon') return [HORIZON_START, HORIZON_END];
  return [from, to];
}

/** Число часов в окне «7-10»: 7, 8, 9 и 10. */
function hoursIn(hours: string): number | null {
  const m = HOURS_PATTERN.exec(hours.trim());
  if (!m) return null;
  const a = Number(m[1]);
  const b = Number(m[2]);
  return a <= b && b <= 23 ? b - a + 1 : null;
}

function monthsBetween(from: string, to: string): number {
  const [y1, m1] = from.split('-').map(Number);
  const [y2, m2] = to.split('-').map(Number);
  return (y2! - y1!) * 12 + (m2! - m1!) + 1;
}

export function ExportSheet({ onClose }: { onClose: () => void }) {
  const day = useStore((s) => dayIndex(s.minute));
  const scenario = useStore((s) => s.scenario);
  const target = useTarget();
  const stops = useStops().data;
  const custom = !isDefaultScenario(scenario);
  const [what, setWhat] = useState<What>(target.level === 'network' ? 'network' : 'target');
  const [period, setPeriod] = useState<Period>('day');
  const [step, setStep] = useState<Step>('hour');
  const [from, setFrom] = useState(HORIZON_START);
  const [to, setTo] = useState(HORIZON_END);
  const [hours, setHours] = useState('');
  const [withScenario, setWithScenario] = useState(custom);
  const [busy, setBusy] = useState<'csv' | 'xlsx' | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', esc);
    return () => document.removeEventListener('keydown', esc);
  }, [onClose]);

  const effectiveStep: Step = period === 'year' ? 'month' : step;
  const [start, end] = range(period, day, from, to);
  const days = Math.max(dayOf(end) - dayOf(start) + 1, 0);
  const hourCount = hours ? hoursIn(hours) : 24;
  const periods = effectiveStep === 'hour' ? days * (hourCount ?? 24)
    : effectiveStep === 'day' ? days : period === 'year' ? 12 : monthsBetween(start, end);
  const objects = what === 'routes' ? ROUTES : what === 'stops' ? stops?.length ?? 0 : 1;
  const rows = objects * periods;
  const problems = [
    period === 'custom' && (dayOf(start) < 0 || dayOf(end) < 0 || start > end)
      ? 'Интервал должен лежать между 1 января 2025 и 31 октября 2026, начало не позже конца.' : null,
    hours && hourCount == null ? 'Часы пишутся как «7-10»: с 7:00 до 10:59.' : null,
    rows > MAX_ROWS ? `Выйдет ${fmtInt(rows)} строк, лист Excel вмещает ${fmtInt(MAX_ROWS)}: сузьте период или возьмите шаг «по суткам».`
      : null,
  ].filter(Boolean) as string[];

  const run = async (format: 'csv' | 'xlsx') => {
    setBusy(format);
    setMessage(null);
    const level = what === 'target' ? targetQuery(target) : { level: what === 'routes' ? 'route' as const
      : what === 'stops' ? 'stop' as const : 'network' as const };
    const { id, ...rest } = level as ReturnType<typeof targetQuery>;
    const when: Partial<SeriesQuery> = period === 'year' ? { horizon: 'year' }
      : { from: start, to: end, granularity: effectiveStep, ...(hours ? { hours: hours.trim() } : {}) };
    try {
      await download(format, { ...rest, ids: id ? [id] : undefined, ...when } as SeriesQuery & { ids?: string[] },
        withScenario ? scenario : { coefficients: {}, events: [] });
      setMessage(`Файл ${format.toUpperCase()} скачан: ${fmtInt(rows)} строк.`);
    } catch (e) {
      setMessage(`Выгрузка не удалась: ${e instanceof Error ? e.message : 'сервис недоступен'}`);
    } finally {
      setBusy(null);
    }
  };

  const whatOptions: { value: What; label: string; hint: string }[] = [
    ...(target.level !== 'network' ? [{ value: 'target' as const, label: target.name, hint: target.subtitle }] : []),
    { value: 'routes', label: 'Все маршруты', hint: '10 маршрутов, как в сабмите' },
    { value: 'stops', label: 'Все остановки', hint: `${stops?.length ?? '...'} остановок, оценка по долям` },
    { value: 'network', label: 'Вся сеть', hint: 'Сумма по 10 маршрутам' },
  ];

  return (
    <div className={sheet.backdrop} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={sheet.sheet} role="dialog" aria-label="Выгрузка прогноза">
        <header>
          <h2>Выгрузка прогноза</h2>
          <button type="button" aria-label="Закрыть" onClick={onClose}><Icon.close /></button>
        </header>

        <section className={styles.group}>
          <h3>Что выгрузить</h3>
          {whatOptions.map((o) => (
            <label key={o.value} className={what === o.value ? styles.optionOn : styles.option}>
              <input type="radio" name="what" checked={what === o.value} onChange={() => setWhat(o.value)} />
              <span><b>{o.label}</b><small>{o.hint}</small></span>
            </label>
          ))}
        </section>

        <section className={styles.group}>
          <h3>Период</h3>
          <div className={styles.wrap}>
            {PERIODS.map((p) => (
              <button key={p.value} type="button" title={p.hint} aria-pressed={period === p.value}
                className={period === p.value ? styles.pillOn : styles.pill} onClick={() => setPeriod(p.value)}>{p.label}</button>
            ))}
          </div>
          {period === 'custom' && (
            <div className={styles.dates}>
              <input type="date" value={from} min={TIMELINE_START} max={TIMELINE_END} aria-label="С даты"
                onChange={(e) => setFrom(e.target.value)} />
              <span>-</span>
              <input type="date" value={to} min={TIMELINE_START} max={TIMELINE_END} aria-label="По дату"
                onChange={(e) => setTo(e.target.value)} />
            </div>
          )}
          <small className={styles.note}>{period === 'year' ? 'Ноябрь 2025 - октябрь 2026' : `${start} - ${end}`}.
            До ноября 2025 - факт, ноябрь-декабрь 2025 - прогноз, 2026 год - оценка; источник в столбце «источник».</small>
        </section>

        <section className={styles.group}>
          <h3>Шаг</h3>
          {period === 'year'
            ? <small className={styles.note}>Годовой прогноз только по месяцам.</small>
            : <Segmented value={step} options={STEPS} onChange={setStep} label="Шаг выгрузки" />}
          {effectiveStep !== 'month' && (
            <label className={styles.hours}>
              Часы
              <input value={hours} placeholder="все, или 7-10" onChange={(e) => setHours(e.target.value)} aria-label="Окно часов" />
            </label>
          )}
        </section>

        {custom && (
          <Toggle checked={withScenario} onChange={setWithScenario} label="С учётом сценария"
            hint="Ползунки и события из вкладки «Сценарий»; без него - прогноз по умолчанию" />
        )}

        <div className={styles.summary}>
          <span>Строк в файле</span>
          <b className="num">{fmtInt(rows)}</b>
        </div>
        {problems.map((p) => <p key={p} className={styles.problem}>{p}</p>)}
        <div className={styles.actions}>
          <button type="button" className={styles.primary} disabled={problems.length > 0 || busy != null}
            onClick={() => void run('xlsx')}><Icon.download />{busy === 'xlsx' ? 'Готовим XLSX…' : 'Скачать XLSX'}</button>
          <button type="button" className={styles.secondary} disabled={problems.length > 0 || busy != null}
            onClick={() => void run('csv')}>{busy === 'csv' ? 'Готовим CSV…' : 'CSV'}</button>
        </div>
        {message && <p className={styles.message} role="status">{message}</p>}
        <p>CSV в UTF-8 с разделителем «;», открывается в Excel. Маршруты по часам за ноябрь-декабрь совпадают с файлом
          сабмита.</p>
      </div>
    </div>
  );
}
