// Где стоит подсказка тура: рядом с подсвеченным блоком, с той стороны, где ей хватает места. Если места нет
// ни с одной стороны, подсказка встаёт по центру экрана. На телефоне она всегда внизу во всю ширину.

export interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface Size {
  width: number;
  height: number;
}

export type Side = 'right' | 'left' | 'bottom' | 'top' | 'center' | 'sheet';

export interface Placement {
  left: number;
  top: number;
  side: Side;
}

/** Зазор между блоком и подсказкой. */
export const GAP = 14;
/** Отступ подсказки и подсветки от края экрана. */
export const MARGIN = 12;
/** Уже этого подсказка встаёт внизу экрана во всю ширину. */
export const SHEET_WIDTH = 640;

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), Math.max(lo, hi));

/** Общая рамка нескольких блоков: время в верхней строке - это кнопка даты и часы рядом. */
export function union(boxes: Box[]): Box | null {
  if (boxes.length === 0) return null;
  const left = Math.min(...boxes.map((b) => b.left));
  const top = Math.min(...boxes.map((b) => b.top));
  const right = Math.max(...boxes.map((b) => b.left + b.width));
  const bottom = Math.max(...boxes.map((b) => b.top + b.height));
  return { left, top, width: right - left, height: bottom - top };
}

/** Подсветка чуть шире блока, но не за краем экрана. */
export function pad(box: Box, by: number, view: Size): Box {
  const left = Math.max(box.left - by, MARGIN / 2);
  const top = Math.max(box.top - by, MARGIN / 2);
  const right = Math.min(box.left + box.width + by, view.width - MARGIN / 2);
  const bottom = Math.min(box.top + box.height + by, view.height - MARGIN / 2);
  return { left, top, width: Math.max(right - left, 0), height: Math.max(bottom - top, 0) };
}

export function placeCard(target: Box | null, card: Size, view: Size): Placement {
  if (view.width < SHEET_WIDTH) {
    return { left: MARGIN, top: Math.max(MARGIN, view.height - card.height - MARGIN), side: 'sheet' };
  }
  const center: Placement = {
    left: clamp((view.width - card.width) / 2, MARGIN, view.width - card.width - MARGIN),
    top: clamp((view.height - card.height) / 2, MARGIN, view.height - card.height - MARGIN),
    side: 'center',
  };
  if (!target) return center;
  const right = target.left + target.width;
  const bottom = target.top + target.height;
  // сколько места остаётся с каждой стороны после подсказки
  const room: Record<'right' | 'left' | 'bottom' | 'top', number> = {
    right: view.width - right - GAP - MARGIN - card.width,
    left: target.left - GAP - MARGIN - card.width,
    bottom: view.height - bottom - GAP - MARGIN - card.height,
    top: target.top - GAP - MARGIN - card.height,
  };
  const sides = Object.keys(room) as (keyof typeof room)[];
  const fitting = sides.filter((s) => room[s] >= 0);
  // низкий блок вроде верхней строки или шкалы времени: подсказка под ним или над ним, как выпадающее окно;
  // высокий вроде карты или панели: сбоку, где свободнее
  const low = target.height < view.height * 0.3;
  const side = low && fitting.some((s) => s === 'bottom' || s === 'top')
    ? (room.bottom >= 0 ? 'bottom' : 'top')
    : fitting.sort((a, b) => room[b] - room[a])[0];
  const alongY = clamp(target.top, MARGIN, view.height - card.height - MARGIN);
  const alongX = clamp(target.left + target.width / 2 - card.width / 2, MARGIN, view.width - card.width - MARGIN);
  switch (side) {
    case 'right': return { left: right + GAP, top: alongY, side };
    case 'left': return { left: target.left - GAP - card.width, top: alongY, side };
    case 'bottom': return { left: alongX, top: bottom + GAP, side };
    case 'top': return { left: alongX, top: target.top - GAP - card.height, side };
    default: return center;
  }
}
