import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useCurrentFrame } from 'remotion';
import { renderFrame, type Nav } from './render';

// Композиция Remotion: один холст, кадр рисуется из номера кадра. Размер холста подстраивается под экран
// показа (не больше 2560 пикселей по ширине), поэтому текст чёткий и на проекторе, и на ноутбуке.

const MAX_PX = 2560;

function backing(): number {
  const cssW = Math.min(window.innerWidth, (window.innerHeight * 16) / 9);
  return Math.max(960, Math.min(MAX_PX, Math.round(cssW * (window.devicePixelRatio || 1))));
}

export function Deck(nav: Nav) {
  const frame = useCurrentFrame();
  const canvas = useRef<HTMLCanvasElement>(null);
  const [px, setPx] = useState(backing);

  useEffect(() => {
    const onResize = () => setPx(backing());
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useLayoutEffect(() => {
    if (canvas.current) renderFrame(canvas.current, frame, nav);
  }, [frame, nav, px]);

  return (
    <canvas ref={canvas} width={px} height={Math.round((px * 9) / 16)}
      style={{ position: 'absolute', inset: 0, width: 1920, height: 1080, display: 'block' }} />
  );
}
