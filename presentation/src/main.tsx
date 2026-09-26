import { StrictMode, useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Player, type PlayerRef } from '@remotion/player';
import { FILM } from './film';
import { Deck } from './deck/Deck';
import { DAY, DUSK, buildRaster, uiRaster } from './deck/map';
import { drawSlide, FPS, SEGMENTS, TOTAL, locate, renderFrame, type Nav } from './deck/render';
import { SLIDES } from './deck/slides';
import { BLUE_STREET, DUSK_STREET, PAPER_STREET } from './deck/street';
import { tram } from './deck/tram';
import './global.css';

// Показ: слайд проигрывает свою анимацию и ждёт. → PgDn пробел клик - следующий с переходом, ← PgUp -
// предыдущий, Home и End - первый и последний, F - полный экран.

function App() {
  const player = useRef<PlayerRef>(null);
  const [slide, setSlide] = useState(0);
  const [nav, setNav] = useState<Nav>({ from: null, fromT: 0, dir: 1 });
  const segment = SEGMENTS[slide]!;

  useEffect(() => {
    const p = player.current;
    if (!p) return;
    p.seekTo(segment.start);
    p.play();
  }, [segment.start, nav]);

  // для проверок и снимков: номер кадра и состояние плеера
  useEffect(() => {
    (window as unknown as { deck: unknown }).deck = {
      frame: () => player.current?.getCurrentFrame(),
      playing: () => player.current?.isPlaying(),
      /** Среднее время кадра слайда i в секунду t, мс: для проверки плавности. */
      bench: (i: number, t: number, n = 20) => {
        const c = FILM.makeCanvas(Math.round(1920 * FILM.S), Math.round(1080 * FILM.S));
        const g = c.getContext('2d', { alpha: false })!;
        const t0 = performance.now();
        for (let k = 0; k < n; k++) drawSlide(g, i, t + k / 60);
        return (performance.now() - t0) / n;
      },
    };
  }, []);

  const go = useCallback((target: number) => {
    const p = player.current;
    if (!p || target < 0 || target >= SLIDES.length) return;
    const { index, t } = locate(p.getCurrentFrame());
    if (target === index) return;
    setNav({ from: index, fromT: t, dir: target > index ? 1 : -1 });
    setSlide(target);
  }, []);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const k = e.key;
      if (['ArrowRight', 'PageDown', ' ', 'Enter'].includes(k)) go(slide + 1);
      else if (['ArrowLeft', 'PageUp', 'Backspace'].includes(k)) go(slide - 1);
      else if (k === 'Home') go(0);
      else if (k === 'End') go(SLIDES.length - 1);
      else if (['f', 'F', 'а', 'А'].includes(k)) {
        if (document.fullscreenElement) void document.exitFullscreen();
        else void document.documentElement.requestFullscreen().catch(() => undefined);
      } else return;
      e.preventDefault();
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [go, slide]);

  return (
    <div style={{ position: 'fixed', inset: 0, background: '#060A1C', cursor: 'pointer' }}
      onClick={(e) => go(slide + (e.clientX < window.innerWidth * 0.2 ? -1 : 1))}>
      <Player ref={player} component={Deck} inputProps={nav} durationInFrames={TOTAL} fps={FPS}
        compositionWidth={1920} compositionHeight={1080} style={{ width: '100%', height: '100%' }}
        controls={false} loop={false} clickToPlay={false} spaceKeyToPlayOrPause={false}
        doubleClickToFullscreen={false} moveToBeginningWhenEnded={false}
        inFrame={segment.start} outFrame={segment.end} initiallyMuted numberOfSharedAudioTags={0} acknowledgeRemotionLicense />
    </div>
  );
}

/** Загрузка: шрифты, снимки экранов, растры карты и тяжёлые фоны строятся до первого кадра. */
async function warm(status: (k: number) => void): Promise<void> {
  await Promise.all([
    ...['200', '300', '400', '500', '600', '700'].map((w) => document.fonts.load(`${w} 40px Onest`)),
    document.fonts.load('600 40px "JetBrains Mono"'),
    document.fonts.load('600 40px "JetBrains Mono"', 'Ё'),
  ]);
  status(0.3);
  const cssW = Math.min(window.innerWidth, (window.innerHeight * 16) / 9);
  const px = Math.max(960, Math.min(2560, Math.round(cssW * (window.devicePixelRatio || 1))));
  FILM.S = px / 1920;
  buildRaster(DAY);
  status(0.55);
  buildRaster(DUSK);
  uiRaster();
  status(0.75);
  const c = FILM.makeCanvas(px, Math.round((px * 9) / 16));
  const g = c.getContext('2d', { alpha: false })!;
  // все растры (вагоны с каждым положением дверей, карточки, карты) строятся до показа, иначе первый кадр
  // нового состояния стоит десятки миллисекунд и рвёт движение
  for (const pal of [PAPER_STREET, BLUE_STREET, DUSK_STREET]) tram(g, 900, 1012, 46, { pal, dir: 1, route: '17', lit: pal === DUSK_STREET });
  // у вагона на остановке десятки состояний дверей и заполнения: сцену прогреваем по всей длине, остальные по трём точкам
  const moments = (i: number): number[] => {
    const d = SLIDES[i]!.dur;
    if (SLIDES[i]!.id !== 'stop') return [0.5, d * 0.5, d + 1];
    return Array.from({ length: Math.ceil(d / 0.1) + 1 }, (_, k) => k * 0.1);
  };
  // переход в каждый слайд целиком: при первом показе он иначе дёргается, пока строятся растры и шейдеры
  for (let i = 0; i < SLIDES.length; i++) {
    for (const t of moments(i)) drawSlide(g, i, t);
    if (i > 0) {
      const nav: Nav = { from: i - 1, fromT: SLIDES[i - 1]!.dur + 1, dir: 1 };
      for (let t = 0; t <= SLIDES[i]!.tr.dur + 0.3; t += 0.1) renderFrame(c, SEGMENTS[i]!.start + Math.round(t * FPS), nav);
    }
    status(0.75 + (0.25 * (i + 1)) / SLIDES.length);
    await new Promise((r) => setTimeout(r, 0));
  }
  status(1);
}

const root = document.getElementById('root')!;
const bar = document.createElement('div');
bar.style.cssText = 'position:fixed;left:50%;top:50%;width:420px;transform:translate(-50%,-50%);font:500 18px "JetBrains Mono",monospace;'
  + 'color:#5B4331;letter-spacing:3px;text-align:center';
bar.innerHTML = 'ЧАС ПИК<div style="margin-top:18px;height:2px;background:rgba(91,67,49,.2)"><i style="display:block;height:100%;width:0;background:#E43D8C;transition:width .3s"></i></div>';
document.body.style.background = '#EDE0C4';
document.body.appendChild(bar);
const fill = bar.querySelector('i')!;

void warm((k) => { fill.style.width = `${k * 100}%`; }).then(() => {
  bar.remove();
  document.body.style.background = '#060A1C';
  createRoot(root).render(<StrictMode><App /></StrictMode>);
});
