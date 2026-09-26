import { useState } from 'react';
import { useRouteStops } from '../../api/queries';
import type { NetworkLoad, RouteStop } from '../../api/types';
import { useStore } from '../../state/store';
import { hourOf } from '../../lib/time';
import { fmtInt } from '../../lib/format';
import { routeColor } from '../../lib/routes';
import { flyTo } from '../map/mapHandle';
import { InfoTip } from '../ui/Controls';
import { Icon } from '../ui/Icons';
import styles from './StopsPanel.module.css';

// Остановки выбранного маршрута отдельной панелью справа от списка маршрутов: список по направлению с
// посадками за выбранный час и выбор участка. По умолчанию панель скрыта, открывается из карточки маршрута.

function lastStop(stops: RouteStop[], direction: number): string {
  const own = stops.filter((s) => s.direction === direction);
  return own.length ? own.reduce((a, b) => (b.seq > a.seq ? b : a)).name : '';
}

export function StopsPanel({ route, load }: { route: number; load: NetworkLoad | undefined }) {
  const stops = useRouteStops(route).data ?? [];
  const setStopsOpen = useStore((s) => s.setStopsOpen);
  const hour = useStore((s) => hourOf(s.minute));
  const segment = useStore((s) => s.segment);
  const [direction, setDirection] = useState(segment?.direction ?? 0);
  const directions = [0, 1].filter((d) => stops.some((s) => s.direction === d));
  const list = stops.filter((s) => s.direction === direction).sort((a, b) => a.seq - b.seq);

  return (
    <section className={styles.panel} style={{ '--c': routeColor(route) } as React.CSSProperties}
      aria-label={`Остановки маршрута ${route}`}>
      <header className={styles.head}>
        <span className={styles.badge}>{route}</span>
        <h2>Остановки</h2>
        <span className={styles.count}>{list.length}</span>
        <button type="button" className={styles.close} aria-label="Скрыть остановки" title="Скрыть панель остановок"
          onClick={() => setStopsOpen(false)}><Icon.close /></button>
      </header>
      <div className={styles.dirs} role="radiogroup" aria-label="Направление">
        {directions.map((d) => (
          <button key={d} type="button" role="radio" aria-checked={direction === d}
            className={direction === d ? styles.dirOn : styles.dir} onClick={() => setDirection(d)}>
            до «{lastStop(stops, d)}»
          </button>
        ))}
      </div>
      <p className={styles.caption}>
        Посадки в {hour}:00–{hour + 1}:00
        <InfoTip>Прогноз маршрута на этот час, разложенный по долям остановок в выбранном направлении. На общей
          с другими маршрутами остановке здесь только этот маршрут. Клик выбирает остановку: прогноз справа
          и графики внизу переключаются на неё и считают все маршруты, карта подлетает к ней.</InfoTip>
      </p>
      <StopList list={list} routeHour={load?.routes.get(route)?.[hour] ?? 0} />
      <SegmentPicker stops={stops} direction={direction} onDirection={setDirection} />
    </section>
  );
}

/** Посадки маршрута в этот час × доля остановки в выбранном направлении, как в «Станциях по дням». Общая
 * с другими маршрутами остановка показывает только этот маршрут, сумму по всем даёт прогноз справа. */
function StopList({ list, routeHour }: { list: RouteStop[]; routeHour: number }) {
  const selected = useStore((s) => s.stop);
  const selectStop = useStore((s) => s.selectStop);
  const segment = useStore((s) => s.segment);
  const values = list.map((s) => s.share * routeHour);
  const max = Math.max(...values, 1);
  const inSegment = (s: RouteStop) => {
    if (!segment || segment.direction !== s.direction) return false;
    const from = list.find((x) => x.stopId === segment.from)?.seq ?? 0;
    const to = list.find((x) => x.stopId === segment.to)?.seq ?? 0;
    return s.seq >= from && s.seq <= to;
  };
  if (list.length === 0) return <p className={styles.caption}>Загружаем остановки…</p>;
  return (
    <ol className={styles.list}>
      {list.map((s, i) => (
        <li key={s.stopId}>
          <button type="button" aria-pressed={selected === s.stopId}
            className={`${selected === s.stopId ? styles.rowOn : styles.row} ${inSegment(s) ? styles.inSegment : ''}`}
            onClick={() => { selectStop(s.stopId); flyTo(s.lon, s.lat, 15.2); }}>
            <span className={styles.seq}>{s.seq}</span>
            <span className={styles.name}>{s.name}</span>
            <span className={styles.bar}><i style={{ width: `${(100 * (values[i] ?? 0)) / max}%` }} /></span>
            <b className="num">{fmtInt(values[i])}</b>
          </button>
        </li>
      ))}
    </ol>
  );
}

/** Участок маршрута: прогноз посадок на остановках между двумя выбранными по ходу движения. */
function SegmentPicker({ stops, direction, onDirection }: {
  stops: RouteStop[];
  direction: number;
  onDirection: (d: number) => void;
}) {
  const segment = useStore((s) => s.segment);
  const setSegment = useStore((s) => s.setSegment);
  const own = (d: number) => stops.filter((s) => s.direction === d).sort((a, b) => a.seq - b.seq);
  const list = own(direction);
  if (list.length < 2) return null;
  const active = segment?.direction === direction ? segment : null;
  const from = active?.from ?? list[0]!.stopId;
  const to = active?.to ?? list[list.length - 1]!.stopId;
  const pick = (a: string, b: string) => {
    const i = Math.max(list.findIndex((s) => s.stopId === a), 0);
    const j = list.findIndex((s) => s.stopId === b);
    const k = j < 0 ? list.length - 1 : j;
    onDirection(direction);
    setSegment({ direction, from: list[Math.min(i, k)]!.stopId, to: list[Math.max(i, k)]!.stopId });
  };
  return (
    <div className={styles.segment}>
      <p className={styles.segTitle}>
        Участок маршрута
        <InfoTip>Посадки на остановках между двумя выбранными по ходу движения: прогноз маршрута делится по долям
          остановок. Прогноз и графики справа переключаются на участок, на карте он подсвечивается.</InfoTip>
      </p>
      <label className={styles.segField}>
        <span>от</span>
        <select value={from} onChange={(e) => pick(e.target.value, to)} aria-label="Первая остановка участка">
          {list.map((s) => <option key={s.stopId} value={s.stopId}>{s.seq}. {s.name}</option>)}
        </select>
      </label>
      <label className={styles.segField}>
        <span>до</span>
        <select value={to} onChange={(e) => pick(from, e.target.value)} aria-label="Последняя остановка участка">
          {list.map((s) => <option key={s.stopId} value={s.stopId}>{s.seq}. {s.name}</option>)}
        </select>
      </label>
      {segment ? (
        <button type="button" className={styles.segBtn} onClick={() => setSegment(null)}>Показать весь маршрут</button>
      ) : (
        <button type="button" className={styles.segBtnPrimary} onClick={() => pick(from, to)}>Прогноз участка</button>
      )}
    </div>
  );
}
