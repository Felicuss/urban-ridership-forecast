import { useEffect } from 'react';
import { useStore } from '../state/store';
import { nowOnTimeline } from '../lib/time';

/**
 * Часы симуляции. При проигрывании время идёт в speed раз быстрее настоящего: ×60 - минута за секунду,
 * ×3600 - сутки за 24 секунды. В режиме «Сейчас» время раз в секунду сверяется с настоящим.
 */
export function useClock(): void {
  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    let lastNow = 0;
    const tick = (t: number) => {
      raf = requestAnimationFrame(tick);
      const dt = Math.min(t - last, 250);
      last = t;
      const s = useStore.getState();
      if (s.followNow) {
        if (t - lastNow > 1000) {
          lastNow = t;
          s.tick(nowOnTimeline());
        }
        return;
      }
      if (s.playing) s.tick(s.minute + (dt / 60_000) * s.speed);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);
}
