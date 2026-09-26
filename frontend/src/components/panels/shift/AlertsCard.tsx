import { useState } from 'react';
import { useRouteStops } from '../../../api/queries';
import { useAlerts, type AlertState } from '../../../hooks/useDispatch';
import { useStore } from '../../../state/store';
import { CAPACITY } from '../../../lib/dispatch';
import { MINUTES_PER_DAY, dayLabel } from '../../../lib/time';
import { fmtInt } from '../../../lib/format';
import { ROUTE_IDS, routeColor } from '../../../lib/routes';
import { Card, TramDots } from '../../ui/Controls';
import { Icon } from '../../ui/Icons';
import styles from './Shift.module.css';

/**
 * Оповещения: подписка на маршрут или участок с порогом посадок на рейс. Проверяется следующий день после
 * выбранного, сработавшие подписки считает колокольчик в верхней строке. Подписки хранятся в браузере.
 */
export function AlertsCard() {
  const { day, states, pending } = useAlerts();
  const removeAlert = useStore((s) => s.removeAlert);
  const fired = states.filter((s) => s.spans.length > 0).length;
  return (
    <Card id="shift-alerts" title={`Оповещения на завтра, ${dayLabel(day, false)}`}
      info="Подпишитесь на маршрут или участок: если завтра поток на рейс выше порога, подписка краснеет, а на колокольчике в верхней строке появляется число. Завтра - следующий день после выбранного на шкале. Подписки хранятся в этом браузере.">
      {states.length === 0 && !pending && (
        <p className={styles.meta}>Подписок нет. Выберите маршрут и порог ниже, участок берётся из панели остановок.</p>
      )}
      {pending && <TramDots label="Проверяем прогноз на завтра" />}
      {states.length > 0 && (
        <p className={styles.meta}>{fired ? `Сработало ${fired} из ${states.length}` : `Все ${states.length} в норме`}</p>
      )}
      <ul className={styles.rows}>
        {states.map((s) => <AlertRow key={s.rule.id} state={s} day={day} onRemove={() => removeAlert(s.rule.id)} />)}
      </ul>
      <AddAlert />
    </Card>
  );
}

function AlertRow({ state, day, onRemove }: { state: AlertState; day: number; onRemove: () => void }) {
  const setMinute = useStore((s) => s.setMinute);
  const selectRoute = useStore((s) => s.selectRoute);
  const { rule, spans, max, maxHour } = state;
  const hot = spans.length > 0;
  return (
    <li className={hot ? styles.alertHot : styles.alertOk}>
      <button type="button" className={styles.rowBtn} title="Показать этот час на карте"
        onClick={() => { selectRoute(rule.route); setMinute(day * MINUTES_PER_DAY + maxHour * 60 + 30); }}>
        <span className={styles.badge} style={{ '--c': routeColor(rule.route) } as React.CSSProperties}>{rule.route}</span>
        <span>{rule.segment ? rule.segment.label : 'весь маршрут'}, порог {rule.limit}</span>
        <small>{hot
          ? spans.map((x) => `${x.from}-${x.to} ч до ${fmtInt(x.peak)}`).join(', ') + ' на рейс'
          : `в норме: максимум ${fmtInt(max)} на рейс в ${maxHour}:00`}</small>
      </button>
      <button type="button" className={styles.remove} aria-label="Удалить подписку" onClick={onRemove}><Icon.close /></button>
    </li>
  );
}

function AddAlert() {
  const selected = useStore((s) => s.route);
  const segment = useStore((s) => s.segment);
  const addAlert = useStore((s) => s.addAlert);
  const [route, setRoute] = useState<number>(selected ?? 17);
  const [limit, setLimit] = useState(CAPACITY);
  const [onSegment, setOnSegment] = useState(false);
  const stops = useRouteStops(route).data;
  const canSegment = segment != null && selected === route;
  const name = (id: string) => stops?.find((s) => s.stopId === id)?.name ?? id;
  const add = () => addAlert({
    route, limit,
    segment: canSegment && onSegment && segment ? { ...segment, label: `${name(segment.from)} → ${name(segment.to)}` } : null,
  });
  return (
    <div className={styles.form}>
      <label className={styles.field}>
        <span>Маршрут</span>
        <select value={route} onChange={(e) => setRoute(Number(e.target.value))}>
          {ROUTE_IDS.map((r) => <option key={r} value={r}>№{r}</option>)}
        </select>
      </label>
      <label className={styles.field}>
        <span>Порог на рейс</span>
        <input type="number" min={20} max={400} step={5} value={limit}
          onChange={(e) => setLimit(Math.min(Math.max(Number(e.target.value) || CAPACITY, 20), 400))} />
      </label>
      <label className={styles.check} title={canSegment ? undefined : 'Выберите участок этого маршрута в панели остановок'}>
        <input type="checkbox" checked={canSegment && onSegment} disabled={!canSegment}
          onChange={(e) => setOnSegment(e.target.checked)} />
        только выбранный участок
      </label>
      <button type="button" className={styles.primary} onClick={add}>Подписаться</button>
    </div>
  );
}
