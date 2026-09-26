import { useEffect } from 'react';
import { ROUTE_IDS } from '../lib/routes';
import { MINUTES_PER_DAY, TIMELINE_DAYS, dayIndex, hourOf } from '../lib/time';
import { useLayout } from '../state/layout';
import { useStore } from '../state/store';

// Клавиши диспетчера: номер маршрута с клавиатуры, матрица станций, день и час без мыши.
//   1 7 - маршрут 17 (цифры набираются подряд, как номер); 0 или Esc - вся сеть
//   S - маршрут по станциям и дням; ← → - день, ↑ ↓ - час (в матрице без Shift, иначе с Shift)
//   V - раскладка: карта, сплит, панели; ? - список клавиш в настройках

/** Сколько ждать вторую цифру номера: «1» может быть началом 11, 12 или 17. */
const DIGIT_WAIT_MS = 700;

function editable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return ['INPUT', 'TEXTAREA', 'SELECT', 'CANVAS'].includes(target.tagName) || target.isContentEditable;
}

export function useHotkeys(): void {
  useEffect(() => {
    let digits = '';
    let timer = 0;
    const commit = () => {
      const route = Number(digits);
      digits = '';
      if (ROUTE_IDS.includes(route)) useStore.getState().selectRoute(route);
    };
    const shift = (days: number, hours: number) => {
      const s = useStore.getState();
      const day = Math.min(Math.max(dayIndex(s.minute) + days, 0), TIMELINE_DAYS - 1);
      const hour = Math.min(Math.max(hourOf(s.minute) + hours, 0), 23);
      s.setMinute(day * MINUTES_PER_DAY + hour * 60 + 30);
    };
    const key = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || editable(e.target)) return;
      const s = useStore.getState();
      if (s.boardOpen) return;
      if (/^[0-9]$/.test(e.key)) {
        window.clearTimeout(timer);
        if (e.key === '0' && digits === '') {
          s.selectRoute(null);
          return;
        }
        digits += e.key;
        const prefix = ROUTE_IDS.filter((r) => String(r).startsWith(digits));
        if (prefix.length === 0) digits = '';
        else if (prefix.length === 1 && String(prefix[0]) === digits) commit();
        else timer = window.setTimeout(commit, DIGIT_WAIT_MS);
        return;
      }
      if (['s', 'S', 'ы', 'Ы'].includes(e.key) && s.route != null) {
        s.setMatrixOpen(!s.matrixOpen);
        e.preventDefault();
        return;
      }
      if (['v', 'V', 'м', 'М'].includes(e.key)) {
        useLayout.getState().cycle();
        return;
      }
      if (e.key === '?') {
        s.setSettingsOpen(true);
        return;
      }
      // Esc в окне выгрузки, календаре или помощнике закрывает только их, выбранный маршрут остаётся
      if (e.key === 'Escape' && !s.matrixOpen && s.route != null && !s.settingsOpen
        && !document.querySelector('[role="dialog"]')) {
        s.selectRoute(null);
        return;
      }
      const arrows = s.matrixOpen || e.shiftKey;
      if (!arrows) return;
      const step: Record<string, [number, number]> = {
        ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1],
      };
      const move = step[e.key];
      if (!move) return;
      e.preventDefault();
      shift(move[0], move[1]);
    };
    document.addEventListener('keydown', key);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener('keydown', key);
    };
  }, []);
}
