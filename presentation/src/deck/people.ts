import { P, lib } from '../film';

// Пассажиры сбоку: осенние пальто и куртки, шапки, шарфы, рюкзаки и телефоны. Руки и ноги ходят в шаг,
// лицо в профиль смотрит туда, куда человек идёт. Всё векторно, контур тушью как у остального листа.

type Hat = 'none' | 'beanie' | 'pompom' | 'cap' | 'ushanka' | 'hood';
type Carry = 'none' | 'backpack' | 'shoulder' | 'briefcase' | 'phone';

export interface Look {
  h: number;
  coat: string;
  coatLen: number;
  pants: string;
  shoes: string;
  hat: Hat;
  hatColor: string;
  hair: string;
  longHair: boolean;
  scarf: string | null;
  carry: Carry;
  bag: string;
  skin: string;
  kid: boolean;
}

const COATS = ['#8E3B3B', '#3C5A7A', '#5E6B3F', '#6B4E7A', '#B0773A', '#2F4A4A', '#7A5230', '#4A4A58', '#C9B28A', '#A34E62', '#35507A'];
const KID_COATS = ['#E0B040', '#D8584A', '#3C8CC8', '#6DAA5C', '#D86A9A'];
const PANTS = ['#2E3440', '#3B4A63', '#4A4540', '#2A2A2E', '#5A5F6B', '#6A5A48'];
const HAT_COLORS = ['#C2413B', '#2F4A6A', '#E0B040', '#3E5E4A', '#6B4E7A', '#2E2A28', '#D8D2C4', '#D86A8A'];
const HAIR = ['#2B2019', '#5A3B22', '#8A6A42', '#C9A66B', '#1E1E22', '#A8A29A'];
const SKIN = ['#EBC9A6', '#E2B894', '#D6A57E', '#F0D2B4', '#C99A72'];
const SCARVES = ['#C2413B', '#E0B040', '#3C6E9E', '#7A9A5A', '#D86A8A', '#F0E6D0'];
const HATS: Hat[] = ['none', 'none', 'beanie', 'beanie', 'pompom', 'cap', 'ushanka', 'hood'];
const CARRY: Carry[] = ['none', 'none', 'backpack', 'backpack', 'shoulder', 'briefcase', 'phone', 'phone'];

type Rng = (() => number) & { range: (a: number, b: number) => number };

const pick = <T>(r: Rng, list: T[]): T => list[Math.floor(r() * list.length) % list.length]!;

export function randomLook(r: Rng): Look {
  const kid = r() < 0.1;
  return {
    h: kid ? r.range(56, 64) : r.range(86, 104),
    coat: kid ? pick(r, KID_COATS) : pick(r, COATS),
    coatLen: kid ? 0.3 : r.range(0.3, 0.52),
    pants: pick(r, PANTS),
    shoes: r() < 0.2 ? '#E8E2D6' : '#231F1C',
    hat: kid ? 'pompom' : pick(r, HATS),
    hatColor: pick(r, HAT_COLORS),
    hair: pick(r, HAIR),
    longHair: !kid && r() < 0.35,
    scarf: r() < 0.45 ? pick(r, SCARVES) : null,
    carry: kid ? 'none' : pick(r, CARRY),
    bag: lib.mix(pick(r, HAT_COLORS), '#000', 0.2),
    skin: pick(r, SKIN),
    kid,
  };
}

type Ctx = CanvasRenderingContext2D;

/** Конечность с контуром: сначала тушь потолще, поверх цвет. */
function limb(ctx: Ctx, pts: [number, number][], w: number, color: string): void {
  ctx.beginPath();
  pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  ctx.strokeStyle = P.ink!;
  ctx.lineWidth = w + 2.2;
  ctx.stroke();
  ctx.strokeStyle = color;
  ctx.lineWidth = w;
  ctx.stroke();
}

function blob(ctx: Ctx, fill: string, lw = 1.3): void {
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = P.ink!;
  ctx.lineWidth = lw;
  ctx.stroke();
}

/**
 * Человек сбоку. x, feet - точка между ступнями; f - куда смотрит (1 вправо, -1 влево); stride от -1 до 1 - фаза
 * шага, 0 - стоит.
 */
export function drawPerson(ctx: Ctx, L: Look, x: number, feet: number, f: number, stride: number, alpha = 1): void {
  if (alpha <= 0) return;
  const h = L.h;
  const walking = Math.abs(stride) > 0.01;
  const bob = walking ? -Math.abs(Math.cos(Math.asin(Math.max(-1, Math.min(1, stride))))) * h * 0.012 : 0;
  const hip = feet - h * 0.46 + bob;
  const sh = feet - h * (L.kid ? 0.74 : 0.8) + bob;
  const headR = h * (L.kid ? 0.1 : 0.074);
  const hy = sh - h * 0.02 - headR * 1.05;
  const hem = sh + (L.coatLen + 0.3) * h * 0.72;
  ctx.save();
  ctx.globalAlpha *= alpha;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  // тень
  ctx.fillStyle = lib.rgba(P.ink!, 0.13);
  ctx.beginPath();
  ctx.ellipse(x + 3, feet + 2, h * 0.2, 3.2, 0, 0, Math.PI * 2);
  ctx.fill();
  // ноги: дальняя темнее
  const leg = (a: number, color: string) => {
    const knee: [number, number] = [x + (a * 0.1 + 0.02 * f) * h, feet - h * 0.23];
    const foot: [number, number] = [x + a * 0.16 * h, feet - h * 0.03];
    limb(ctx, [[x, hip], knee, foot], h * 0.075, color);
    ctx.beginPath();
    ctx.ellipse(foot[0] + f * h * 0.035, feet - h * 0.018, h * 0.055, h * 0.025, 0, 0, Math.PI * 2);
    blob(ctx, L.shoes, 1);
  };
  leg(-stride, lib.mix(L.pants, '#000', 0.25));
  // дальняя рука
  const swing = L.carry === 'phone' ? 0 : stride * 0.5;
  const arm = (a: number, color: string, front: boolean) => {
    const s0: [number, number] = [x + (front ? 0.03 : -0.02) * f * h, sh + h * 0.04];
    if (front && L.carry === 'phone') {
      // телефон у груди, экран светится к лицу
      const hand: [number, number] = [x + f * h * 0.13, sh + h * 0.12];
      limb(ctx, [s0, [x + f * h * 0.04, sh + h * 0.22], hand], h * 0.062, color);
      ctx.save();
      ctx.translate(hand[0], hand[1] - h * 0.02);
      ctx.rotate(-f * 0.5);
      ctx.fillStyle = '#1B1D22';
      ctx.fillRect(-h * 0.02, -h * 0.045, h * 0.04, h * 0.07);
      ctx.fillStyle = 'rgba(170,215,255,0.9)';
      ctx.fillRect(-h * 0.014, -h * 0.039, h * 0.028, h * 0.056);
      ctx.restore();
      ctx.beginPath();
      ctx.arc(hand[0], hand[1], h * 0.03, 0, Math.PI * 2);
      blob(ctx, L.skin, 1);
      return;
    }
    const len = h * 0.32;
    const elbow: [number, number] = [s0[0] + Math.sin(a) * len * 0.5 * f, s0[1] + Math.cos(a) * len * 0.5];
    const hand: [number, number] = [elbow[0] + Math.sin(a * 1.3 + 0.12) * len * 0.5 * f, elbow[1] + Math.cos(a * 1.3) * len * 0.5];
    limb(ctx, [s0, elbow, hand], h * 0.062, color);
    ctx.beginPath();
    ctx.arc(hand[0], hand[1], h * 0.032, 0, Math.PI * 2);
    blob(ctx, L.skin, 1);
    if (front && L.carry === 'briefcase') {
      ctx.beginPath();
      ctx.roundRect(hand[0] - h * 0.09, hand[1] + h * 0.02, h * 0.18, h * 0.13, h * 0.02);
      blob(ctx, '#4A3526');
    }
  };
  arm(-swing, lib.mix(L.coat, '#000', 0.22), false);
  leg(stride, L.pants);
  // рюкзак за спиной
  if (L.carry === 'backpack') {
    ctx.beginPath();
    ctx.roundRect(x - f * h * 0.2 - h * 0.06, sh + h * 0.05, h * 0.13, h * 0.26, h * 0.04);
    blob(ctx, L.bag);
  }
  // пальто или куртка: плечи, трапеция к подолу
  ctx.beginPath();
  ctx.moveTo(x - h * 0.1, sh + h * 0.03);
  ctx.quadraticCurveTo(x, sh - h * 0.04, x + h * 0.1, sh + h * 0.03);
  ctx.lineTo(x + h * 0.125 + f * h * 0.01, hem);
  ctx.quadraticCurveTo(x, hem + h * 0.02, x - h * 0.125 + f * h * 0.01, hem);
  ctx.closePath();
  blob(ctx, L.coat, 1.4);
  ctx.strokeStyle = lib.rgba(P.ink!, 0.45);
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x + f * h * 0.045, sh + h * 0.03);
  ctx.lineTo(x + f * h * 0.06, hem - h * 0.01);
  ctx.moveTo(x + f * h * 0.02, hip - h * 0.02);
  ctx.lineTo(x + f * h * 0.09, hip - h * 0.02);
  ctx.stroke();
  if (L.carry === 'shoulder') {
    ctx.strokeStyle = '#3A2B20';
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.moveTo(x + f * h * 0.06, sh + h * 0.02);
    ctx.lineTo(x - f * h * 0.1, hip);
    ctx.stroke();
    ctx.beginPath();
    ctx.roundRect(x - f * h * 0.14 - h * 0.06, hip - h * 0.03, h * 0.12, h * 0.1, h * 0.02);
    blob(ctx, '#6B4A32');
  }
  // шарф: узел у шеи и хвост за спиной
  if (L.scarf) {
    ctx.beginPath();
    ctx.ellipse(x, sh + h * 0.01, h * 0.085, h * 0.035, 0, 0, Math.PI * 2);
    blob(ctx, L.scarf, 1.1);
    ctx.beginPath();
    ctx.roundRect(x - f * h * 0.08 - h * 0.022, sh + h * 0.02, h * 0.044, h * 0.17, h * 0.01);
    blob(ctx, L.scarf, 1.1);
  }
  arm(swing, L.coat, true);
  // длинные волосы спадают на спину
  if (L.longHair && L.hat !== 'hood') {
    ctx.beginPath();
    ctx.roundRect(x - f * headR * 0.2 - headR * 0.85, hy, headR * 1.7, headR * 2.3, headR * 0.6);
    blob(ctx, L.hair, 1.1);
  }
  // капюшон вокруг головы
  if (L.hat === 'hood') {
    ctx.beginPath();
    ctx.arc(x - f * headR * 0.15, hy - headR * 0.05, headR * 1.3, 0, Math.PI * 2);
    blob(ctx, lib.mix(L.coat, '#000', 0.12), 1.3);
  }
  // голова: волосы сзади, лицо в профиль, нос и глаз
  ctx.beginPath();
  ctx.arc(x, hy, headR, 0, Math.PI * 2);
  blob(ctx, L.hat === 'hood' ? L.skin : L.hair, 1.2);
  ctx.beginPath();
  ctx.ellipse(x + f * headR * 0.22, hy + headR * 0.14, headR * 0.8, headR * 0.84, 0, 0, Math.PI * 2);
  ctx.fillStyle = L.skin;
  ctx.fill();
  ctx.beginPath();
  ctx.arc(x + f * headR * 0.98, hy + headR * 0.12, headR * 0.22, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = P.ink!;
  ctx.beginPath();
  ctx.arc(x + f * headR * 0.5, hy - headR * 0.08, Math.max(0.8, headR * 0.1), 0, Math.PI * 2);
  ctx.fill();
  hat(ctx, L, x, hy, headR, f);
  ctx.restore();
}

function hat(ctx: Ctx, L: Look, x: number, hy: number, r: number, f: number): void {
  if (L.hat === 'none' || L.hat === 'hood') return;
  const dome = (k: number, color: string) => {
    ctx.beginPath();
    ctx.arc(x, hy - r * 0.12, r * k, Math.PI, 0);
    ctx.closePath();
    blob(ctx, color, 1.2);
  };
  if (L.hat === 'ushanka') {
    ctx.beginPath();
    ctx.roundRect(x - f * r * 0.75 - r * 0.32, hy - r * 0.3, r * 0.64, r * 1.05, r * 0.3);
    blob(ctx, '#7A6A58', 1.1);
    dome(1.18, '#7A6A58');
    ctx.beginPath();
    ctx.roundRect(x - r * 1.2, hy - r * 0.32, r * 2.4, r * 0.38, r * 0.15);
    blob(ctx, '#8F7E6A', 1.1);
    return;
  }
  dome(1.08, L.hatColor);
  if (L.hat === 'cap') {
    ctx.beginPath();
    ctx.ellipse(x + f * r * 1.05, hy - r * 0.16, r * 0.6, r * 0.14, 0, 0, Math.PI * 2);
    blob(ctx, L.hatColor, 1.1);
    return;
  }
  ctx.beginPath();
  ctx.roundRect(x - r * 1.1, hy - r * 0.34, r * 2.2, r * 0.36, r * 0.12);
  blob(ctx, lib.mix(L.hatColor, '#fff', 0.2), 1.1);
  if (L.hat === 'pompom') {
    ctx.beginPath();
    ctx.arc(x, hy - r * 1.3, r * 0.34, 0, Math.PI * 2);
    blob(ctx, lib.mix(L.hatColor, '#fff', 0.45), 1.1);
  }
}
