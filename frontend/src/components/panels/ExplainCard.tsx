import { useExplain } from '../../api/queries';
import type { ExplainStep } from '../../api/types';
import { useStore } from '../../state/store';
import { fmtInt, fmtPct } from '../../lib/format';
import { Card } from '../ui/Controls';
import styles from './ExplainCard.module.css';

// Водопад «из чего сложился прогноз»: посадки за сутки после каждого шага формулы сервиса, от профиля
// последних недель до итога. Шаги считает сервис (/api/v1/forecast/explain), последний равен прогнозу.

const STEP: Record<ExplainStep['key'], { label: string; hint: string }> = {
  profile: { label: 'Профиль истории',
    hint: 'Посадки в такой же день недели по последним неделям истории до 31 октября 2025, на этот час и маршрут' },
  level: { label: 'Уровень месяца',
    hint: 'Как спрос меняется от октября к ноябрю и декабрю: трамвай Москвы прошлых лет по data.mos.ru, ползунки «Спрос в ноябре» и «в декабре»' },
  calendar: { label: 'Календарь',
    hint: 'Праздник в будний день, рабочая суббота 1 ноября, 29-30 и 31 декабря, бесплатный проезд в новогоднюю ночь' },
  network: { label: 'События сети',
    hint: 'Выходные маршрутов 7 и 50 снова по всей трассе с 15.11, Т1 с 12.11, запуск маршрута 5 16.12: посты Дептранса' },
  weather: { label: 'Погода', hint: 'Осадки и мороз по Open-Meteo; в прогнозе по умолчанию выключена, включается на вкладке «Сценарий»' },
  model: { label: 'Модель v11',
    hint: 'LightGBM и сезонная модель долей часов поправляют формулу в каждом часе: форма суток по маршрутам, распределение посадок между днями, режимы маршрутов, которых нет в правилах, например выходные №50 до 9 ноября' },
  scenario: { label: 'Сценарий', hint: 'Перекрытия, мероприятия и сбои, добавленные на вкладке «Сценарий»' },
};

/** Шаг меньше половины посадки считаем пустым: так и не рисуем, и перечисляем одной строкой. */
const EMPTY = 0.5;

export function ExplainCard({ route, date, title }: { route: number | null; date: string; title: string }) {
  const scenario = useStore((s) => s.scenario);
  const { data: steps } = useExplain(route, date, scenario, true);
  if (!steps?.length) return null;
  const total = steps[steps.length - 1]!.value;
  const max = Math.max(...steps.map((s) => s.value), 1);
  const [first, ...rest] = steps;
  const shown = rest.filter((s) => Math.abs(s.delta) >= EMPTY);
  const quiet = rest.filter((s) => Math.abs(s.delta) < EMPTY).map((s) => STEP[s.key].label.toLowerCase());
  const pct = (x: number) => `${(100 * x) / max}%`;

  return (
    <Card title="Из чего сложился прогноз"
      info={`${title}, посадки за сутки после каждого шага формулы сервиса. Первая полоса - профиль последних недель, дальше вклад каждого шага, последняя - прогноз. Ползунки сценария меняют полосу своего шага.`}>
      <ol className={styles.list}>
        <li title={STEP.profile.hint}>
          <span className={styles.label}>{STEP.profile.label}</span>
          <span className={styles.track}><i className={styles.base} style={{ left: 0, width: pct(first!.value) }} /></span>
          <b className="num">{fmtInt(first!.value)}</b>
        </li>
        {shown.map((s) => {
          const before = s.value - s.delta;
          const up = s.delta > 0;
          const share = before > 0 ? (100 * s.delta) / before : null;
          return (
            <li key={s.key} title={STEP[s.key].hint}>
              <span className={styles.label}>{STEP[s.key].label}</span>
              <span className={styles.track}>
                <i className={up ? styles.up : styles.down}
                  style={{ left: pct(Math.min(before, s.value)), width: pct(Math.abs(s.delta)) }} />
              </span>
              <b className={`num ${up ? styles.plus : styles.minus}`}>
                {up ? '+' : '−'}{fmtInt(Math.abs(s.delta))}
                {share != null && <small> {fmtPct(share).replace('-', '−')}</small>}
              </b>
            </li>
          );
        })}
        <li className={styles.total}>
          <span className={styles.label}>Прогноз</span>
          <span className={styles.track}><i className={styles.base} style={{ left: 0, width: pct(total) }} /></span>
          <b className="num">{fmtInt(total)}</b>
        </li>
      </ol>
      {quiet.length > 0 && <p className={styles.quiet}>Без изменений в этот день: {quiet.join(', ')}.</p>}
    </Card>
  );
}
