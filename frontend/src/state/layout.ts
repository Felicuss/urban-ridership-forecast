import { create } from 'zustand';

// Раскладка главной области: карта во весь экран, сплит (карта и виджет рядом) или панели виджетов без карты.
// В каждом месте виджет выбирается из списка и переставляется перетаскиванием за заголовок. Выбор хранится
// в браузере, как флаги слоёв.

export type LayoutMode = 'map' | 'split' | 'panels';
export type WidgetKind = 'forecast' | 'stations' | 'brief' | 'bottlenecks' | 'fleet' | 'alerts';
export type PanelsCount = 2 | 3 | 4;

const KEY = 'tram-ui.layout.v1';
const KINDS: WidgetKind[] = ['forecast', 'stations', 'brief', 'bottlenecks', 'fleet', 'alerts'];
const DEFAULT_WIDGETS: WidgetKind[] = ['stations', 'forecast', 'bottlenecks', 'brief'];

interface Saved {
  mode: LayoutMode;
  widgets: WidgetKind[];
  count: PanelsCount;
}

function load(): Saved {
  const fallback: Saved = { mode: 'map', widgets: DEFAULT_WIDGETS, count: 4 };
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return fallback;
    const p = JSON.parse(raw) as Partial<Saved>;
    const widgets = Array.isArray(p.widgets) && p.widgets.length === 4 && p.widgets.every((w) => KINDS.includes(w))
      ? p.widgets : DEFAULT_WIDGETS;
    const mode = p.mode === 'split' || p.mode === 'panels' ? p.mode : 'map';
    const count = p.count === 2 || p.count === 3 ? p.count : 4;
    return { mode, widgets, count };
  } catch {
    return fallback;
  }
}

function save(s: Saved): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    // приватный режим браузера: раскладка живёт до перезагрузки
  }
}

interface LayoutState extends Saved {
  setMode: (mode: LayoutMode) => void;
  /** Следующая раскладка по кругу: карта, сплит, панели. */
  cycle: () => void;
  setWidget: (slot: number, kind: WidgetKind) => void;
  swap: (a: number, b: number) => void;
  setCount: (count: PanelsCount) => void;
}

export const useLayout = create<LayoutState>((set, get) => {
  const persist = (patch: Partial<Saved>) => {
    const next = { mode: get().mode, widgets: get().widgets, count: get().count, ...patch };
    save(next);
    set(patch);
  };
  return {
    ...load(),
    setMode: (mode) => persist({ mode }),
    cycle: () => {
      const order: LayoutMode[] = ['map', 'split', 'panels'];
      persist({ mode: order[(order.indexOf(get().mode) + 1) % order.length]! });
    },
    setWidget: (slot, kind) => persist({ widgets: get().widgets.map((w, i) => (i === slot ? kind : w)) }),
    swap: (a, b) => {
      const w = [...get().widgets];
      [w[a], w[b]] = [w[b]!, w[a]!];
      persist({ widgets: w });
    },
    setCount: (count) => persist({ count }),
  };
});
