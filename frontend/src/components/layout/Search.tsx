import { useMemo, useState } from 'react';
import { useStops } from '../../api/queries';
import { useStore } from '../../state/store';
import { ROUTE_COLORS, routeColor } from '../../lib/routes';
import { flyTo } from '../map/mapHandle';
import styles from './Search.module.css';

const LIMIT = 8;

/** Поиск остановки по названию или маршрута по номеру: выбор подсвечивает объект и приближает карту. */
export function Search() {
  const stops = useStops().data;
  const selectStop = useStore((s) => s.selectStop);
  const selectRoute = useStore((s) => s.selectRoute);
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const query = q.trim().toLowerCase();
  const results = useMemo(() => {
    if (!query) return [];
    const routes = Object.keys(ROUTE_COLORS).filter((r) => r.startsWith(query))
      .map((r) => ({ kind: 'route' as const, id: r, name: `Маршрут ${r}`, routes: [Number(r)] }));
    const byName = (stops ?? []).filter((s) => s.name.toLowerCase().includes(query))
      .sort((a, b) => Number(!a.name.toLowerCase().startsWith(query)) - Number(!b.name.toLowerCase().startsWith(query)))
      .map((s) => ({ kind: 'stop' as const, id: s.id, name: s.name, routes: s.routes, lat: s.lat, lon: s.lon }));
    return [...routes, ...byName].slice(0, LIMIT);
  }, [query, stops]);

  const pick = (r: (typeof results)[number]) => {
    if (r.kind === 'route') {
      selectRoute(Number(r.id));
    } else {
      selectStop(r.id);
      if ('lat' in r) flyTo(r.lon, r.lat, 15.5);
    }
    setQ('');
    setOpen(false);
  };

  return (
    <div className={styles.box}>
      <input className={styles.input} value={q} placeholder="Остановка или номер маршрута" aria-label="Поиск"
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && results[0]) pick(results[0]);
          if (e.key === 'Escape') setOpen(false);
        }} />
      {open && results.length > 0 && (
        <ul className={styles.list} role="listbox">
          {results.map((r) => (
            <li key={`${r.kind}-${r.id}`}>
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => pick(r)}>
                <span>{r.name}</span>
                <span className={styles.chips}>
                  {r.routes.slice(0, 4).map((n) => <i key={n} style={{ color: routeColor(n) }}>{n}</i>)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
