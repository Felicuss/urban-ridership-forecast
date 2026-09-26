import { Suspense, useState, type ReactNode } from 'react';
import { useLayout, type PanelsCount, type WidgetKind } from '../../state/layout';
import { useStore } from '../../state/store';
import { ForecastTab } from '../panels/ForecastTab';
import { StationMatrix } from '../panels/StationMatrix';
import { AlertsCard } from '../panels/shift/AlertsCard';
import { BottlenecksCard } from '../panels/shift/BottlenecksCard';
import { BriefCard } from '../panels/shift/BriefCard';
import { FleetCard } from '../panels/shift/FleetCard';
import { TramDots } from '../ui/Controls';
import styles from './Workspace.module.css';

// Виджеты для сплита и панелей: те же блоки, что во вкладках, но их можно держать на экране одновременно.
// Все виджеты смотрят на общие выбор маршрута и время, поэтому клавиши и шкала двигают их вместе.

const WIDGETS: { kind: WidgetKind; label: string }[] = [
  { kind: 'stations', label: 'Станции по дням' },
  { kind: 'forecast', label: 'Прогноз' },
  { kind: 'bottlenecks', label: 'Узкие места недели' },
  { kind: 'brief', label: 'Сводка смены' },
  { kind: 'fleet', label: 'Калькулятор выпуска' },
  { kind: 'alerts', label: 'Оповещения' },
];

function Stations() {
  const route = useStore((s) => s.route);
  if (route == null) {
    return <p className={styles.empty}>Выберите маршрут в списке слева или наберите номер цифрами, например 1 7.</p>;
  }
  return <StationMatrix key={route} route={route} embedded />;
}

function render(kind: WidgetKind): ReactNode {
  switch (kind) {
    case 'forecast': return <ForecastTab />;
    case 'stations': return <Stations />;
    case 'bottlenecks': return <BottlenecksCard />;
    case 'brief': return <BriefCard />;
    case 'fleet': return <FleetCard />;
    case 'alerts': return <AlertsCard />;
  }
}

/** Место под виджет: заголовок с выбором и ручкой перетаскивания, ниже сам виджет с прокруткой. */
function Slot({ index }: { index: number }) {
  const kind = useLayout((s) => s.widgets[index] ?? 'forecast');
  const setWidget = useLayout((s) => s.setWidget);
  const swap = useLayout((s) => s.swap);
  const [over, setOver] = useState(false);
  return (
    <section className={over ? styles.slotOver : styles.slot}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const from = Number(e.dataTransfer.getData('text/plain'));
        if (Number.isInteger(from) && from !== index) swap(from, index);
      }}>
      <header className={styles.head} draggable
        onDragStart={(e) => { e.dataTransfer.setData('text/plain', String(index)); e.dataTransfer.effectAllowed = 'move'; }}
        title="Перетащите заголовок на другое место, чтобы поменять виджеты местами">
        <span className={styles.grip} aria-hidden="true">⠿</span>
        <select value={kind} aria-label="Что показать на этом месте" onChange={(e) => setWidget(index, e.target.value as WidgetKind)}>
          {WIDGETS.map((w) => <option key={w.kind} value={w.kind}>{w.label}</option>)}
        </select>
      </header>
      <div className={styles.body}>
        <Suspense fallback={<TramDots label="Загружаем" />}>{render(kind)}</Suspense>
      </div>
    </section>
  );
}

/** Правая половина сплита: один виджет рядом с картой. */
export function SplitPane() {
  return <div className={styles.split}><Slot index={0} /></div>;
}

const COUNTS: { value: PanelsCount; label: string }[] = [
  { value: 2, label: '2' },
  { value: 3, label: '3' },
  { value: 4, label: '4' },
];

/** Панели без карты: два, три или четыре виджета сеткой. */
export function PanelsBoard() {
  const count = useLayout((s) => s.count);
  const setCount = useLayout((s) => s.setCount);
  return (
    <div className={styles.board}>
      <div className={styles.toolbar}>
        <span>Панелей на экране</span>
        {COUNTS.map((c) => (
          <button key={c.value} type="button" className={count === c.value ? styles.countOn : styles.count}
            onClick={() => setCount(c.value)}>{c.label}</button>
        ))}
        <small>Виджет выбирается в заголовке панели, место меняется перетаскиванием заголовка.</small>
      </div>
      <div className={styles.grid} data-count={count}>
        {Array.from({ length: count }, (_, i) => <Slot key={i} index={i} />)}
      </div>
    </div>
  );
}
