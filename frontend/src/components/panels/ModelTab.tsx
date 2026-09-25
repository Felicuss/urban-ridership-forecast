import { useMeta } from '../../api/queries';
import type { Granularity } from '../../api/types';
import { fmt1 } from '../../lib/format';
import { Card, Kpi, TramDots } from '../ui/Controls';
import styles from './Panels.module.css';

// Проверки факторов на эталоне организаторов 25.09.2026: разница точности с фактором и без него
// (docs/analysis/README.md, п. 5.2).
const EVIDENCE = [
  { factor: 'Выходные 7 и 50 снова по полной трассе с 15.11', effect: 1.16 },
  { factor: 'Запуск маршрута 5 16.12 около 18:00', effect: 0.41 },
  { factor: 'Календарные правила: праздники, рабочая суббота, 31.12', effect: 0.14 },
  { factor: 'Поправка на фактическую погоду (выключена)', effect: -0.26 },
  { factor: 'Прогноз v6 вместо формулы профиля: LightGBM, поправки уровня и долей часов', effect: 0.6 },
];

const GRANULARITY: { key: Granularity; label: string }[] = [
  { key: 'hour', label: 'по часам' },
  { key: 'day', label: 'по суткам' },
  { key: 'month', label: 'по месяцам' },
];

export default function ModelTab() {
  const meta = useMeta().data;
  if (!meta) return <TramDots label="Загружаем паспорт модели" />;
  const q = meta.quality;
  const folds = Object.keys(q.folds);
  const score = meta.leaderboardWapeScore;
  const pos = (v: number) => `${Math.min(Math.max(((v - 0.8) / 0.12) * 100, 0), 100)}%`;
  const check = q.year.index_check_city_tram;

  return (
    <div className={styles.stack}>
      <Card title="Точность на проверке организаторов"
        info="Организаторы сравнили прогноз с фактом за ноябрь-декабрь 2025 по каждому маршруту и часу: точность = 1 - сумма ошибок / сумма посадок (WAPE-score). Выше 0,88 критерий точности даёт максимум баллов.">
        <div className={styles.big}>{score.toFixed(5)}</div>
        <div className={styles.gauge}><i style={{ width: pos(score) }} /><b style={{ left: pos(0.88) }} /></div>
        <p className={styles.note}>Шкала 0,80-0,92, жёлтая отметка - порог 0,88. По умолчанию сервис отдаёт прогноз v6:
          адаптивные профили, ансамбль LightGBM, поправки дневного уровня и долей часов. В нём есть открытые данные,
          вышедшие после {meta.forecastOrigin}: организаторы это разрешили. Ползунки сдвигают v6 так же, как формулу
          профиля.</p>
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

      <Card title="Проверка на прошлых месяцах" info={`${q.scheme}. Модель строила прогноз от даты в прошлом, зная только то, что было до неё, и сравнивалась с фактом следующих 1-2 месяцев. Точность от 0 до 1, чем ближе к 1, тем лучше. Это проверка формулы профиля, на которой работают ползунки; v6 проверили организаторы: 0,90553.`}>
        <table className={styles.table}>
          <thead>
            <tr><th>период</th>{GRANULARITY.map((g) => <th key={g.key}>{g.label}</th>)}</tr>
          </thead>
          <tbody>
            {folds.map((f) => (
              <tr key={f}>
                <td title={q.folds[f]}>{q.folds[f]?.split(': ')[1]?.replace(' -> ', ', прогноз на ') ?? f}</td>
                {GRANULARITY.map((g) => <td key={g.key} className="num">{q.wape_score[g.key][f]?.toFixed(3)}</td>)}
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

      <Card title="Область применимости">
        <ul className={styles.list}>
          {meta.applicability.map((a) => <li key={a}><span>{a}</span></li>)}
          <li><span>Остановок в сети: {q.stops.stops}; {q.stops.osm_matched_to_reference} из {q.stops.osm_stops} остановок OSM
            совпали со справочником организаторов ближе 40 м.</span></li>
        </ul>
      </Card>

      <p className={styles.note}>Модель {meta.modelVersion}, коммит {meta.gitCommit.slice(0, 7)}, артефакты от {meta.generatedAt.slice(0, 10)}.
        Файл прогноза по умолчанию: {meta.defaultSubmission}.</p>
    </div>
  );
}
