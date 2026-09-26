import { useFactors, useMeta } from '../../api/queries';
import { useStore } from '../../state/store';
import { MINUTES_PER_DAY, dayOf, fullDate, shortDate } from '../../lib/time';
import type { Granularity } from '../../api/types';
import { fmt1, fmtFixed, fmtInt, plural } from '../../lib/format';
import { Card, Kpi, TramDots } from '../ui/Controls';
import styles from './Panels.module.css';

// Проверки факторов на эталоне организаторов 25.09.2026: разница точности с фактором и без него
// (docs/analysis/README.md, п. 5.2).
const EVIDENCE = [
  { factor: 'Выходные 7 и 50 снова по полной трассе с 15.11', effect: 1.16 },
  { factor: 'Запуск маршрута 5 16.12 около 18:00', effect: 0.41 },
  { factor: 'Календарные правила: праздники, рабочая суббота, 31.12', effect: 0.14 },
  { factor: 'Поправка на фактическую погоду (выключена)', effect: -0.26 },
  { factor: 'Прогноз v11 вместо формулы профиля: LightGBM, сезонная модель долей часов, распределение по дням', effect: 0.79 },
];

const GRANULARITY: { key: Granularity; label: string }[] = [
  { key: 'hour', label: 'по часам' },
  { key: 'day', label: 'по суткам' },
  { key: 'month', label: 'по месяцам' },
];

/** Фолд по дате отсечки из подписи «W: до 31.01 -> февраль-март»: таблица идёт по порядку года, а не по буквам. */
function foldOrder(label: string | undefined): number {
  const m = /до (\d{1,2})\.(\d{1,2})/.exec(label ?? '');
  return m ? Number(m[2]) * 100 + Number(m[1]) : Number.MAX_SAFE_INTEGER;
}

/** Часы [1, 2, 3, 5] одной строкой: «1:00–4:00, 5:00–6:00». */
function hourSpans(hours: number[]): string {
  const spans: [number, number][] = [];
  for (const h of [...hours].sort((a, b) => a - b)) {
    const last = spans[spans.length - 1];
    if (last && last[1] === h) last[1] = h + 1;
    else spans.push([h, h + 1]);
  }
  return spans.map(([a, b]) => `${a}:00–${b}:00`).join(', ');
}

export default function ModelTab() {
  const meta = useMeta().data;
  const factors = useFactors().data;
  const checks = factors?.equipment_checks;
  const gaps = factors?.gaps;
  const selectRoute = useStore((s) => s.selectRoute);
  const setMinute = useStore((s) => s.setMinute);
  const setTab = useStore((s) => s.setTab);
  if (!meta) return <TramDots label="Загружаем паспорт модели" />;
  const q = meta.quality;
  const folds = Object.keys(q.folds).sort((a, b) => foldOrder(q.folds[a]) - foldOrder(q.folds[b]));
  const score = meta.leaderboardWapeScore;
  const pos = (v: number) => `${Math.min(Math.max(((v - 0.8) / 0.12) * 100, 0), 100)}%`;
  const check = q.year.index_check_city_tram;

  return (
    <div className={styles.stack}>
      <Card title="Точность на проверке организаторов"
        info="Организаторы сравнили прогноз с фактом за ноябрь-декабрь 2025 по каждому маршруту и часу: точность = 1 - сумма ошибок / сумма посадок (WAPE-score). Выше 0,88 критерий точности даёт максимум баллов.">
        <div className={styles.big}>{fmtFixed(score, 5)}</div>
        <div className={styles.gauge}><i style={{ width: pos(score) }} /><b style={{ left: pos(0.88) }} /></div>
        <p className={styles.note}>Шкала 0,80–0,92, жёлтая отметка — порог 0,88. По умолчанию сервис отдаёт прогноз v11:
          адаптивные профили, ансамбль LightGBM, сезонная модель долей часов и распределение объёма между днями. В нём
          есть открытые данные, вышедшие после {fullDate(meta.forecastOrigin)}: организаторы это разрешили. Ползунки сдвигают
          v11 так же, как формулу профиля.</p>
      </Card>

      <Card title="Что дало точность" info="Насколько выросла или упала точность на проверке организаторов, когда фактор включали и выключали, в процентных пунктах.">
        <table className={styles.table}>
          <tbody>
            {EVIDENCE.map((e) => (
              <tr key={e.factor}>
                <td>{e.factor}</td>
                <td className="num" style={{ color: e.effect >= 0 ? 'var(--ok)' : 'var(--red)', whiteSpace: 'nowrap' }}>
                  {e.effect > 0 ? '+' : ''}{e.effect.toFixed(2).replace('.', ',')} п. п.</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Проверка на прошлых месяцах" info={`${q.scheme}. Модель строила прогноз от даты в прошлом, зная только то, что было до неё, и сравнивалась с фактом следующих 1–2 месяцев. Точность от 0 до 1, чем ближе к 1, тем лучше. Это проверка формулы профиля, на которой работают ползунки; v11 проверили организаторы: ${fmtFixed(score, 5)}.`}>
        <table className={styles.table}>
          <thead>
            <tr><th>период</th>{GRANULARITY.map((g) => <th key={g.key}>{g.label}</th>)}</tr>
          </thead>
          <tbody>
            {folds.map((f) => (
              <tr key={f}>
                <td title={q.folds[f]}>{q.folds[f]?.split(': ')[1]?.replace(' -> ', ', прогноз на ') ?? f}</td>
                {GRANULARITY.map((g) => <td key={g.key} className="num">{fmtFixed(q.wape_score[g.key][f], 3)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className={styles.split}>
        {GRANULARITY.map((g) => (
          <Kpi key={g.key} label={`Коридор ${g.label}`} value={`${Math.round(q.interval_coverage_leave_one_fold_out[g.key] * 100)} %`}
            sub={`ожидалось ${Math.round(q.interval_nominal * 100)} %`}
            info="Как часто факт попадал в коридор прогноза на месяцах, по которым коридор не считали." />
        ))}
        <Kpi label="Ошибка годового прогноза" value={`${fmt1(check.mape_pct)} %`} sub={`в среднем за ${check.months} мес., максимум ${fmt1(check.max_abs_error_pct)} %`}
          info="Насколько сезонный индекс угадал городской трамвай в ноябре 2025 - августе 2026 (данные data.mos.ru вышли позже прогноза)." />
      </div>

      {checks && (
        <Card title="Очистка факта"
          info="Организаторы 26.09.2026: валидации в часы, когда трамваи не ходят, - это проверка оборудования, их нужно отбрасывать. Прогноз v11 в эти часы и так нулевой.">
          <p className={styles.note}>Отброшено {fmtInt(checks.validations)}
            {' '}{plural(checks.validations, ['валидация', 'валидации', 'валидаций'])} в {checks.cells}
            {' '}{plural(checks.cells, ['часе', 'часах', 'часах'])}, это
            {' '}{String(checks.share_pct).replace('.', ',')} % факта января-октября 2025.
            Маршрут работает {checks.window}, ниже - часы вне этого окна.</p>
          <ul className={styles.list}>
            {Object.entries(checks.off_hours).filter(([, h]) => h.length).map(([route, hours]) => (
              <li key={route}><span>№{route}: {hourSpans(hours)}</span></li>
            ))}
          </ul>
        </Card>
      )}

      {gaps && gaps.periods.length > 0 && (
        <Card title="Пропуски в данных"
          info={`Пропуск - ${gaps.rule}. Восстановление ${gaps.restore}. Факт остаётся фактом: восстановленные посадки показаны пунктиром на графике и в прогноз не подмешиваются.`}>
          <ul className={styles.gapList}>
            {gaps.periods.map((g) => (
              <li key={`${g.route}-${g.from}`}>
                <button type="button" className={styles.gapItem} title="Показать этот день на графике"
                  onClick={() => { selectRoute(g.route); setMinute(dayOf(g.from) * MINUTES_PER_DAY + 8 * 60 + 30); setTab('forecast'); }}>
                  <b>№{g.route} · {shortDate(g.from)}{g.to !== g.from ? `-${shortDate(g.to)}` : ''} · {g.days} дн. ({g.day_kinds})</b>
                  <span>{g.reason}</span>
                  <small>факт {fmtInt(g.fact)}, восстановлено {fmtInt(g.restored)} посадок{g.source ? ' · есть пост Дептранса' : ''}</small>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Область применимости">
        <ul className={styles.list}>
          {meta.applicability.map((a) => <li key={a}><span>{a}</span></li>)}
          <li><span>Остановок в сети: {q.stops.stops}; {q.stops.osm_matched_to_reference} из {q.stops.osm_stops} остановок OSM
            совпали со справочником организаторов ближе 40 м.</span></li>
        </ul>
      </Card>

      <p className={styles.note}>Модель {meta.modelVersion}, коммит {meta.gitCommit.slice(0, 7)}, артефакты от {fullDate(meta.generatedAt)}.
        Файл прогноза по умолчанию: {meta.defaultSubmission}.</p>
    </div>
  );
}
