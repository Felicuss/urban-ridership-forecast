import { useAlerts } from '../../hooks/useDispatch';
import { useStore } from '../../state/store';
import { AlertsCard } from './shift/AlertsCard';
import { BottlenecksCard } from './shift/BottlenecksCard';
import { BriefCard } from './shift/BriefCard';
import { FleetCard } from './shift/FleetCard';
import panels from './Panels.module.css';
import styles from './shift/Shift.module.css';

// Вкладка «Смена»: инструменты диспетчера на день и неделю. Сверху оглавление, чтобы не листать до нужного.

const SECTIONS = [
  { id: 'shift-brief', label: 'Сводка' },
  { id: 'shift-alerts', label: 'Оповещения' },
  { id: 'shift-bottlenecks', label: 'Узкие места' },
  { id: 'shift-fleet', label: 'Выпуск' },
];

export default function ShiftTab() {
  const fired = useAlerts().states.filter((s) => s.spans.length > 0).length;
  const route = useStore((s) => s.route);
  const selectRoute = useStore((s) => s.selectRoute);
  return (
    <div className={panels.stack}>
      <nav className={styles.nav} aria-label="Разделы смены">
        {SECTIONS.map((s) => (
          <button key={s.id} type="button"
            onClick={() => document.getElementById(s.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
            {s.label}{s.id === 'shift-alerts' && fired > 0 && <i>{fired}</i>}
          </button>
        ))}
      </nav>
      <p className={styles.scope}>
        {route != null ? <>Смена по маршруту <b>№{route}</b>.{' '}
          <button type="button" onClick={() => selectRoute(null)}>Показать всю сеть</button></>
          : 'Смена по всей сети. Выберите маршрут слева, чтобы смотреть только его.'}
      </p>
      <BriefCard />
      {/* key: при смене маршрута формы подписки и выпуска берут его заново */}
      <AlertsCard key={`alerts-${route ?? 'all'}`} />
      <BottlenecksCard />
      <FleetCard key={`fleet-${route ?? 'all'}`} />
    </div>
  );
}
