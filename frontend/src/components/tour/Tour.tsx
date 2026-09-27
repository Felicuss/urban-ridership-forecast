import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useLayout, type LayoutMode } from '../../state/layout';
import { useStore } from '../../state/store';
import { MINUTES_PER_DAY, dayIndex, nowOnTimeline } from '../../lib/time';
import { Icon } from '../ui/Icons';
import { MARGIN, SHEET_WIDTH, pad, placeCard, union, type Box, type Placement } from './place';
import { LAYOUT_STEPS } from './layoutSteps';
import { STEPS, type TourStep } from './steps';
import styles from './Tour.module.css';

// Тур по разделам: экран затемнён, подсвеченный блок остаётся живым, с ним можно работать прямо во время тура.
// Клики мимо него перехватывают четыре прозрачные шторки вокруг подсветки. Сам открывается при первом входе,
// потом по кнопке «?» в верхней строке.

const SEEN_KEY = 'tram-ui.tour.v1';
const LAYOUT_SEEN_KEY = 'tram-ui.layout-tour.v1';
const seenThisSession = new Set<string>();

/** Тур уже показывали в этом браузере: закончили или пропустили. */
export function tourSeen(key = SEEN_KEY): boolean {
  if (seenThisSession.has(key)) return true;
  try {
    return localStorage.getItem(key) != null;
  } catch {
    return false;
  }
}

function markSeen(key: string): void {
  seenThisSession.add(key);
  try {
    localStorage.setItem(key, new Date().toISOString());
  } catch {
    // приватный режим браузера: до перезагрузки тур сам не откроется
  }
}

const boxOf = (el: Element): Box => {
  const r = el.getBoundingClientRect();
  return { left: r.left, top: r.top, width: r.width, height: r.height };
};

const shown = (el: Element) => {
  const b = boxOf(el);
  return b.width > 0 && b.height > 0;
};

const viewport = () => ({ width: window.innerWidth, height: window.innerHeight });

function targetsOf(selectors: string[] | undefined): Element[] {
  return (selectors ?? []).flatMap((sel) => Array.from(document.querySelectorAll(sel))).filter(shown);
}

export function Tour() {
  const open = useStore((s) => s.tourOpen);
  const setTourOpen = useStore((s) => s.setTourOpen);
  return open ? <TourRun steps={STEPS} seenKey={SEEN_KEY} finale onClose={() => setTourOpen(false)} /> : null;
}

/**
 * Тур по раскладкам: сам открывается, когда раскладку впервые переключили с карты на сплит или панели,
 * и по кнопке «?» в заголовке виджета. После тура остаётся та раскладка, которую выбрал диспетчер.
 */
export function LayoutTour() {
  const open = useStore((s) => s.layoutTourOpen);
  const setOpen = useStore((s) => s.setLayoutTourOpen);
  const mode = useLayout((s) => s.mode);
  const prev = useRef(mode);
  useEffect(() => {
    const from = prev.current;
    prev.current = mode;
    if (from === 'map' && mode !== 'map' && !tourSeen(LAYOUT_SEEN_KEY) && !useStore.getState().tourOpen) setOpen(true);
  }, [mode, setOpen]);
  return open ? <TourRun steps={LAYOUT_STEPS} seenKey={LAYOUT_SEEN_KEY} onClose={() => setOpen(false)} /> : null;
}

function TourRun({ steps: STEPS, seenKey, finale = false, onClose }: {
  steps: TourStep[];
  seenKey: string;
  /** Последний шаг предлагает пустить время с утра: у основного тура. */
  finale?: boolean;
  onClose: () => void;
}) {
  const [index, setIndex] = useState(0);
  const [hole, setHole] = useState<Box | null>(null);
  const [place, setPlace] = useState<Placement | null>(null);
  const card = useRef<HTMLDivElement>(null);
  const primary = useRef<HTMLButtonElement>(null);
  /** Раскладка до тура: тур переключает раскладки под шаги, а при закрытии она возвращается. */
  const layoutBefore = useRef<LayoutMode>(useLayout.getState().mode);
  /** Вкладка правой панели до тура: закрытый на полпути тур возвращает её. */
  const tabBefore = useRef(useStore.getState().tab);
  /** Время до тура: тур ставит утренний пик 18 ноября, а закрытый тур возвращает день, час и режим «Сейчас». */
  const timeBefore = useRef((({ minute, playing, speed, followNow }) => ({ minute, playing, speed, followNow }))(useStore.getState()));
  const step = STEPS[index]!;
  const last = index === STEPS.length - 1;

  const go = useCallback((delta: number) => {
    setIndex((i) => Math.min(Math.max(i + delta, 0), STEPS.length - 1));
  }, []);

  const close = useCallback((restore = true) => {
    markSeen(seenKey);
    if (restore && useLayout.getState().mode !== layoutBefore.current) useLayout.getState().setMode(layoutBefore.current);
    if (restore) {
      useStore.getState().setTab(tabBefore.current);
      const t = timeBefore.current;
      useStore.setState({ ...t, minute: t.followNow ? nowOnTimeline() : t.minute, nowNotice: null });
    }
    onClose();
  }, [seenKey, onClose]);

  const playDay = () => {
    const day = dayIndex(useStore.getState().minute);
    useStore.setState({ minute: day * MINUTES_PER_DAY + 5 * 60, speed: 100, playing: true, followNow: false,
      nowNotice: null });
    close(false);
  };

  // экран под шаг: вкладка правой панели, карта вместо панелей, время утреннего пика
  useEffect(() => {
    if (step.tab) useStore.getState().setTab(step.tab);
    const layout = useLayout.getState();
    if (step.map && layout.mode === 'panels') layout.setMode('map');
    step.prepare?.();
  }, [step]);

  const measure = useCallback(() => {
    const view = viewport();
    const box = union(targetsOf(step.targets).map(boxOf));
    const lit = box && pad(box, 6, view);
    setHole(lit);
    const c = card.current;
    if (c) setPlace(placeCard(lit, { width: c.offsetWidth, height: c.offsetHeight }, view));
  }, [step]);

  // на планшете и телефоне страница прокручивается: блок шага сначала доезжает до экрана
  useLayoutEffect(() => {
    const first = targetsOf(step.targets)[0];
    if (first) {
      const b = boxOf(first);
      const phone = window.innerWidth < SHEET_WIDTH;
      if (b.top < 0 || b.top + b.height > window.innerHeight) first.scrollIntoView({ block: phone ? 'start' : 'center' });
    }
    measure();
    // вкладки правой панели грузятся отдельными чанками: рамка догоняет их, когда они дорисуются
    const timers = [80, 320, 900].map((ms) => window.setTimeout(measure, ms));
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [measure, step]);

  useEffect(() => {
    const onChange = () => measure();
    window.addEventListener('resize', onChange);
    window.addEventListener('scroll', onChange, true);
    const observer = new ResizeObserver(onChange);
    targetsOf(step.targets).forEach((el) => observer.observe(el));
    if (card.current) observer.observe(card.current);
    return () => {
      window.removeEventListener('resize', onChange);
      window.removeEventListener('scroll', onChange, true);
      observer.disconnect();
    };
  }, [measure, step]);

  useEffect(() => {
    primary.current?.focus({ preventScroll: true });
  }, [index]);

  // клавиши тура раньше клавиш диспетчера: Esc закрывает тур и не сбрасывает маршрут, стрелки листают шаги
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const t = e.target;
      if (t instanceof HTMLElement && (['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName) || t.isContentEditable)) return;
      const action: Record<string, () => void> = {
        Escape: () => close(),
        ArrowRight: () => go(1),
        ArrowLeft: () => go(-1),
        '?': () => undefined,
      };
      const run = action[e.key];
      if (!run) return;
      e.preventDefault();
      e.stopPropagation();
      run();
    };
    window.addEventListener('keydown', key, true);
    return () => window.removeEventListener('keydown', key, true);
  }, [close, go]);

  return (
    <div className={styles.root}>
      {hole ? (
        <>
          <div className={styles.shade} style={{ left: 0, right: 0, top: 0, height: hole.top }} />
          <div className={styles.shade} style={{ left: 0, right: 0, top: hole.top + hole.height, bottom: 0 }} />
          <div className={styles.shade} style={{ left: 0, top: hole.top, width: hole.left, height: hole.height }} />
          <div className={styles.shade} style={{ left: hole.left + hole.width, right: 0, top: hole.top, height: hole.height }} />
          <div className={styles.hole} style={{ left: hole.left, top: hole.top, width: hole.width, height: hole.height }} />
        </>
      ) : <div className={styles.dim} />}

      <div ref={card} className={styles.card} role="dialog" aria-modal="true" aria-labelledby="tour-title"
        aria-describedby="tour-text" data-side={place?.side ?? 'center'}
        style={place ? { left: place.left, top: place.top } : { left: MARGIN, top: MARGIN, visibility: 'hidden' }}>
        <div className={styles.progress} aria-hidden="true">
          {STEPS.map((s, i) => <i key={s.title} className={i <= index ? styles.done : undefined} />)}
        </div>
        <div className={styles.head}>
          <span className={styles.count}>Шаг {index + 1} из {STEPS.length}</span>
          <button type="button" className={styles.close} aria-label="Закрыть тур" title="Закрыть тур (Esc)"
            onClick={() => close()}><Icon.close /></button>
        </div>
        <h2 id="tour-title" className={styles.title}>{step.title}</h2>
        <p id="tour-text" className={styles.text}>{step.text}</p>
        {step.hint && <p className={styles.hint}>{step.hint}</p>}
        <div className={styles.buttons}>
          {index === 0
            ? <button type="button" className={styles.quiet} onClick={() => close()}>Пропустить</button>
            : <button type="button" className={styles.quiet} onClick={() => go(-1)}>Назад</button>}
          {last && !finale ? (
            <button ref={primary} type="button" className={styles.primary} onClick={() => close()}>Понятно</button>
          ) : last ? (
            <>
              <button type="button" className={styles.second} onClick={() => close()}>Закончить</button>
              <button ref={primary} type="button" className={styles.primary} onClick={playDay}>
                <Icon.play />Пустить время
              </button>
            </>
          ) : (
            <button ref={primary} type="button" className={styles.primary} onClick={() => go(1)}>
              {index === 0 ? 'Начать' : 'Дальше'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
