// Глобальный объект движка рисования до загрузки lib.js: кадр 1920 × 1080, масштаб растра и время кипения
// линий. lib.js (procedural-film, MIT) читает их через window.FILM, как в презентации LCT_2026.

const film = {
  W: 1920,
  H: 1080,
  /** Пикселей холста на логический пиксель кадра. */
  S: 1,
  /** Время кадра в секундах: по нему линии «кипят» 12 раз в секунду. */
  frameT: 0,
  TIMELINE: { shots: new Array(40) },
  makeCanvas(w: number, h: number): HTMLCanvasElement {
    const c = document.createElement('canvas');
    c.width = w;
    c.height = h;
    return c;
  },
};

(window as unknown as { FILM: typeof film }).FILM = film;

export {};
