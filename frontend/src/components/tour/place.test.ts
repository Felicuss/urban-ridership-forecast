import { describe, expect, it } from 'vitest';
import { GAP, MARGIN, pad, placeCard, union } from './place';

const view = { width: 1600, height: 900 };
const card = { width: 360, height: 220 };

describe('подсказка тура', () => {
  it('встаёт под низким блоком верхней строки и не выходит за правый край', () => {
    const actions = { left: 1180, top: 8, width: 410, height: 40 };
    const p = placeCard(actions, card, view);
    expect(p.side).toBe('bottom');
    expect(p.top).toBe(8 + 40 + GAP);
    expect(p.left + card.width).toBeLessThanOrEqual(view.width - MARGIN);
  });

  it('встаёт над шкалой времени внизу экрана', () => {
    const p = placeCard({ left: 320, top: 726, width: 860, height: 164 }, card, view);
    expect(p.side).toBe('top');
    expect(p.top).toBe(726 - GAP - card.height);
  });

  it('встаёт сбоку от высокой правой панели', () => {
    const p = placeCard({ left: 1190, top: 66, width: 400, height: 824 }, card, view);
    expect(p.side).toBe('left');
    expect(p.left).toBe(1190 - GAP - card.width);
  });

  it('без блока и без места стоит по центру', () => {
    expect(placeCard(null, card, view).side).toBe('center');
    expect(placeCard({ left: 0, top: 0, width: 1600, height: 900 }, card, view).side).toBe('center');
  });

  it('на телефоне всегда внизу экрана', () => {
    const p = placeCard({ left: 10, top: 10, width: 100, height: 40 }, card, { width: 390, height: 800 });
    expect(p).toEqual({ left: MARGIN, top: 800 - card.height - MARGIN, side: 'sheet' });
  });

  it('объединяет кнопку даты и часы в одну рамку и не выводит подсветку за экран', () => {
    const box = union([{ left: 170, top: 8, width: 300, height: 40 }, { left: 480, top: 10, width: 220, height: 36 }]);
    expect(box).toEqual({ left: 170, top: 8, width: 530, height: 40 });
    expect(pad({ left: 2, top: 2, width: 100, height: 40 }, 6, view).left).toBe(MARGIN / 2);
  });
});
