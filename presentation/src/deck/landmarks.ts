import { lib, type Pt } from '../film';

// Силуэты Москвы для полосы улицы: координаты в пикселях панорамы шириной 1920, y вверх со знаком минус от
// земли. У каждого слайда своё место: Лужники с МГУ, Москва-Сити, Кремль, Большой театр, ВДНХ, Крымский мост.

export type Shape = Pt[];

export interface Colored {
  shape: Shape;
  color: string;
  smooth?: boolean;
}

interface Piece {
  shapes?: Shape[];
  windows?: Pt[];
  stars?: Pt[];
  lattice?: [Pt, Pt][];
  /** Фигуры со своим цветом: купола, стекло, кирпич; рисуются по порядку поверх фона. */
  colored?: Colored[];
}

export interface Skyline {
  back: Shape[];
  front: Shape[];
  colored: Colored[];
  windows: Pt[];
  stars: Pt[];
  lattice: [Pt, Pt][];
  trees: Shape[];
}

export type Scene = 'classic' | 'vdnh' | 'city' | 'luzhniki' | 'kremlin' | 'theatre' | 'bridge' | 'panorama';

const BRICK = '#C0715C';
const TENT = '#6E9272';
const CREAM = '#E9DDC2';
const GOLD = '#D2AE58';
const GLASS = ['#B7C6CE', '#A6B9C4', '#C4D0D5'];

function rect(x: number, w: number, h: number, y0 = 0): Shape {
  return [[x, -y0], [x, -y0 - h], [x + w, -y0 - h], [x + w, -y0]];
}

function vline(x: number, y0: number, y1: number): [Pt, Pt] {
  return [[x, y0], [x, y1]];
}

/** Сталинская высотка: ступенчатая башня со шпилем и звездой, крылья по бокам. wing растягивает крылья (МГУ). */
function stalinka(x: number, wing = 1): Piece {
  const ww = 55 * wing;
  const shapes: Shape[] = [
    rect(x - 40 - ww, ww, 46), rect(x + 40, ww, 46),
    rect(x - 40, 80, 70), rect(x - 30, 60, 40, 70), rect(x - 20, 40, 30, 110), rect(x - 12, 24, 22, 140),
    [[x - 5, -162], [x, -206], [x + 5, -162]],
  ];
  const windows: Pt[] = [];
  for (let r = 0; r < 5; r++) for (let c = 0; c < 6; c++) windows.push([x - 32 + c * 12, -12 - r * 11]);
  for (let r = 0; r < 3; r++) for (let c = 0; c < 4; c++) windows.push([x - 20 + c * 12, -80 - r * 10]);
  const cols = Math.floor((ww - 10) / 12);
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < cols; c++) {
      windows.push([x - 40 - ww + 7 + c * 12, -10 - r * 11]);
      windows.push([x + 47 + c * 12, -10 - r * 11]);
    }
  }
  return { shapes, windows, stars: [[x, -210]] };
}

/** Спасская башня: ступени, шатёр и звезда; в Кремле кирпичная с зелёным шатром. */
function spasskaya(x: number, brick = false): Piece {
  const body = [rect(x - 18, 36, 70), rect(x - 14, 28, 26, 70), rect(x - 10, 20, 16, 96)];
  const tent: Shape = [[x - 10, -112], [x, -150], [x + 10, -112]];
  const windows: Pt[] = [[x - 3, -84], [x + 3, -84], [x, -40]];
  if (!brick) return { shapes: [...body, tent, rect(x - 60, 42, 30), rect(x + 18, 42, 30)], windows, stars: [[x, -154]] };
  return {
    colored: [...body.map((shape) => ({ shape, color: BRICK })), { shape: tent, color: TENT }],
    windows,
    lattice: [[[x - 18, -58], [x + 18, -58]], [[x - 14, -84], [x + 14, -84]]],
    stars: [[x, -154]],
  };
}

/** Кремлёвская стена: кирпич и зубцы «ласточкин хвост». */
function kremlinWall(x0: number, x1: number): Piece {
  const h = 30;
  const pts: Pt[] = [[x0, 0], [x0, -h]];
  for (let x = x0 + 3; x + 9 <= x1; x += 14) pts.push([x, -h], [x, -h - 10], [x + 4.5, -h - 6], [x + 9, -h - 10], [x + 9, -h]);
  pts.push([x1, -h], [x1, 0]);
  return { colored: [{ shape: pts, color: BRICK }] };
}

/** Шуховская башня: сетчатые секции, каждая уже предыдущей. */
function shukhov(x: number): Piece {
  const shapes: Shape[] = [];
  const lattice: [Pt, Pt][] = [];
  let y = 0;
  let w = 44;
  for (let k = 0; k < 6; k++) {
    const h = 30 - k * 2;
    const top = w * 0.78;
    shapes.push([[x - w / 2, -y], [x - top / 2 + 3, -y - h / 2], [x - top / 2, -y - h], [x + top / 2, -y - h], [x + top / 2 - 3, -y - h / 2], [x + w / 2, -y]]);
    for (let i = 0; i <= 6; i++) {
      const u = i / 6;
      lattice.push([[x - w / 2 + w * u, -y], [x - top / 2 + top * (1 - u), -y - h]]);
    }
    y += h;
    w = top;
  }
  return { shapes, lattice };
}

/** Останкинская башня: ножки, сужающийся ствол, «бублик» и антенна. */
function ostankino(x: number): Piece {
  return {
    shapes: [
      [[x - 26, 0], [x - 6, -46], [x + 6, -46], [x + 26, 0], [x + 12, 0], [x, -26], [x - 12, 0]],
      [[x - 6, -46], [x - 3, -250], [x + 3, -250], [x + 6, -46]],
      rect(x - 13, 26, 10, 180), rect(x - 9, 18, 6, 198),
      [[x - 1.5, -250], [x - 1, -330], [x + 1, -330], [x + 1.5, -250]],
    ],
  };
}

/** Лужники: колоннада Большой спортивной арены и светлое кольцо крыши над ней. */
function luzhniki(x: number): Piece {
  const W = 178;
  const wall = -40;
  const top = (u: number) => wall - 20 * Math.sqrt(Math.max(0, 1 - u * u));
  const arc: Pt[] = [];
  for (let i = 0; i <= 24; i++) {
    const u = -1 + i / 12;
    arc.push([x + W * u, top(u)]);
  }
  const colored: Colored[] = [
    { shape: [[x - W, 0], [x - W, wall], ...arc.slice(1, -1), [x + W, wall], [x + W, 0]], color: '#A8936E' },
    { shape: [...arc.map(([px, py]): Pt => [px, py - 11]), ...[...arc].reverse()], color: '#F6F2EA' },
  ];
  for (let px = x - W + 8; px < x + W - 8; px += 13) colored.push({ shape: rect(px, 6, -wall - 6, 3), color: '#EFE5CE' });
  colored.push({ shape: rect(x - W - 4, 2 * W + 8, 4), color: '#EFE5CE' });
  return { colored };
}

/** Москва-Сити: «Империя» с дугой, закрученная «Эволюция», «Федерация», золотистый «Меркурий», ОКО, «Город столиц». */
function moscowCity(x: number): Piece {
  const colored: Colored[] = [];
  const lattice: [Pt, Pt][] = [];
  const floors = (l: number, r: number, h: number, slope = 0) => {
    for (let y = 14; y < h - 12; y += 13) lattice.push([[l + 2, -y], [r - 2, -y - slope]]);
  };
  const tower = (shape: Shape, color: string, l: number, r: number, h: number, slope = 0) => {
    colored.push({ shape, color });
    floors(l, r, h, slope);
  };
  let l = x - 160;
  tower([[l, 0], [l, -176], [l + 12, -186], [l + 26, -190], [l + 38, -188], [l + 38, 0]], GLASS[1]!, l, l + 38, 176);
  l = x - 112;
  tower([[l, 0], [l, -226], [l + 15, -234], [l + 30, -226], [l + 30, 0]], GLASS[0]!, l, l + 30, 226, 9);
  l = x - 64;
  tower([[l, 0], [l, -214], [l + 30, -244], [l + 30, 0]], GLASS[2]!, l, l + 30, 214);
  l = x - 26;
  tower([[l, 0], [l, -292], [l + 18, -334], [l + 36, -292], [l + 36, 0]], GLASS[0]!, l, l + 36, 292);
  lattice.push([[l + 18, -334], [l + 18, -366]]);
  l = x + 22;
  tower([[l, 0], [l, -262], [l + 10, -284], [l + 26, -276], [l + 32, -256], [l + 32, 0]], '#C9A874', l, l + 32, 256);
  l = x + 66;
  tower([[l, 0], [l, -300], [l + 30, -294], [l + 30, 0]], GLASS[1]!, l, l + 30, 294);
  l = x + 100;
  tower(rect(l, 24, 206), GLASS[2]!, l, l + 24, 206);
  l = x + 136;
  const steps: Shape = [[l, 0], [l, -62], [l + 5, -62], [l + 5, -124], [l, -124], [l, -186], [l + 5, -186], [l + 5, -250], [l + 36, -250],
    [l + 36, -186], [l + 41, -186], [l + 41, -124], [l + 36, -124], [l + 36, -62], [l + 41, -62], [l + 41, 0]];
  tower(steps, GLASS[0]!, l + 4, l + 37, 250);
  return { colored, lattice };
}

/** Луковичный купол: основание на высоте by, радиус r. */
function onion(cx: number, by: number, r: number): Shape {
  const half: Pt[] = [[0.62, 0], [0.95, -0.4], [1.0, -0.75], [0.82, -1.15], [0.45, -1.55], [0.15, -1.95], [0, -2.25]];
  const right = half.map(([u, v]): Pt => [cx + u * r, by + v * r]);
  const left = [...half].reverse().slice(1).map(([u, v]): Pt => [cx - u * r, by + v * r]);
  return [...right, ...left];
}

/** Собор Василия Блаженного: центральный шатёр, вокруг барабаны с цветными луковицами, звонница. */
function basil(x: number): Piece {
  const colored: Colored[] = [{ shape: rect(x - 70, 140, 40), color: BRICK }];
  const lattice: [Pt, Pt][] = [];
  const domes: [number, number, number, string][] = [
    [-52, -68, 10, '#5F8F6A'], [-30, -88, 12, '#C65A4A'], [30, -86, 12, '#5D86A8'], [52, -70, 10, GOLD], [0, -60, 9, '#D9C48E'],
  ];
  colored.push({ shape: rect(x - 11, 22, 55, 40), color: BRICK });
  colored.push({ shape: [[x - 14, -95], [x, -160], [x + 14, -95]], color: '#D9C48E' });
  colored.push({ shape: onion(x, -160, 5), color: GOLD, smooth: true });
  lattice.push([[x, -171], [x, -180]]);
  for (const [dx, top, r, color] of domes) {
    colored.push({ shape: rect(x + dx - r * 0.6, r * 1.2, -top - 40, 40), color: BRICK });
    colored.push({ shape: onion(x + dx, top, r), color, smooth: true });
    lattice.push([[x + dx, top - r * 2.25], [x + dx, top - r * 2.25 - 8]]);
    lattice.push([[x + dx - r * 0.7, top - r * 0.5], [x + dx + r * 0.5, top - r * 1.4]]);
  }
  colored.push({ shape: rect(x + 78, 14, 90), color: BRICK });
  colored.push({ shape: [[x + 76, -90], [x + 85, -122], [x + 94, -90]], color: TENT });
  colored.push({ shape: onion(x + 85, -122, 4), color: GOLD, smooth: true });
  const windows: Pt[] = [];
  for (let c = 0; c < 9; c++) windows.push([x - 60 + c * 15, -20]);
  return { colored, lattice, windows };
}

/** Большой театр: портик на восьми колоннах, фронтон и квадрига над ним. */
function bolshoi(x: number): Piece {
  const lattice: [Pt, Pt][] = [];
  const colored: Colored[] = [
    { shape: rect(x - 86, 172, 6), color: CREAM },
    { shape: rect(x - 78, 156, 10, 62), color: CREAM },
    { shape: [[x - 84, -72], [x, -98], [x + 84, -72]], color: CREAM },
  ];
  for (let i = 0; i < 8; i++) colored.push({ shape: rect(x - 73 + i * 20, 7, 56, 6), color: '#F3ECDD' });
  colored.push({
    shape: [[x - 16, -98], [x - 16, -105], [x - 11, -111], [x - 7, -107], [x - 3, -114], [x - 2, -124], [x + 2, -124], [x + 3, -114],
      [x + 8, -117], [x + 12, -109], [x + 16, -104], [x + 16, -98]],
    color: '#7D6A45',
  });
  lattice.push([[x - 82, -72], [x + 82, -72]]);
  return { shapes: [[[x - 110, 0], [x - 110, -90], [x - 86, -104], [x + 86, -104], [x + 110, -90], [x + 110, 0]]], colored, lattice };
}

/** Проём арки: прямоугольник с полукруглым верхом. */
function arch(cx: number, w: number, h: number): Shape {
  const pts: Pt[] = [[cx - w / 2, 0], [cx - w / 2, -h + w / 2]];
  for (let i = 1; i < 12; i++) {
    const a = Math.PI + (i / 12) * Math.PI;
    pts.push([cx + Math.cos(a) * (w / 2), -h + w / 2 + Math.sin(a) * (w / 2)]);
  }
  pts.push([cx + w / 2, -h + w / 2], [cx + w / 2, 0]);
  return pts;
}

/** Главный вход ВДНХ: трёхпролётная арка, аттик и золотая скульптура со снопом. */
function vdnhArch(x: number): Piece {
  const lattice: [Pt, Pt][] = [];
  for (const dx of [-72, -66, -30, -24, 24, 30, 66, 72]) lattice.push(vline(x + dx, -2, -66));
  return {
    colored: [
      { shape: rect(x - 80, 160, 70), color: CREAM },
      { shape: arch(x, 34, 54), color: '#9C8A6A' },
      { shape: arch(x - 48, 20, 38), color: '#9C8A6A' },
      { shape: arch(x + 48, 20, 38), color: '#9C8A6A' },
      { shape: rect(x - 66, 132, 16, 70), color: CREAM },
      {
        shape: [[x - 15, -86], [x - 13, -100], [x - 9, -111], [x - 6, -123], [x - 3, -134], [x - 9, -142], [x, -160], [x + 9, -142],
          [x + 3, -134], [x + 6, -123], [x + 9, -111], [x + 13, -100], [x + 15, -86]],
        color: GOLD,
      },
    ],
    lattice,
  };
}

/** Крымский мост: два портала-пилона, цепи с подвесками и полотно. */
function krymsky(x: number): Piece {
  const P1 = x - 120;
  const P2 = x + 120;
  const top = -120;
  const deck = -30;
  const shapes: Shape[] = [rect(x - 270, 540, 6, -deck - 6)];
  for (const px of [P1, P2]) {
    shapes.push([[px - 12, 0], [px - 7, top], [px - 2, top], [px - 5, 0]]);
    shapes.push([[px + 5, 0], [px + 2, top], [px + 7, top], [px + 12, 0]]);
  }
  const lattice: [Pt, Pt][] = [];
  const chain = (x0: number, y0: number, x1: number, y1: number, sag: number) => {
    const pts: Pt[] = [];
    for (let i = 0; i <= 16; i++) {
      const u = i / 16;
      pts.push([lib.lerp(x0, x1, u), lib.lerp(y0, y1, u) + sag * 4 * u * (1 - u)]);
    }
    for (let i = 1; i < pts.length; i++) lattice.push([pts[i - 1]!, pts[i]!]);
    for (let i = 1; i < pts.length - 1; i += 1) lattice.push([pts[i]!, [pts[i]![0], deck - 6]]);
  };
  chain(P1, top, P2, top, 82);
  chain(x - 262, deck - 6, P1, top, -8);
  chain(P2, top, x + 262, deck - 6, -8);
  for (const px of [P1, P2]) lattice.push([[px - 7, top + 20], [px + 7, top + 20]], [[px - 6, top + 60], [px + 6, top + 60]]);
  return { shapes, lattice };
}

function house(x: number, w: number, h: number, floors: number): { shape: Shape; windows: Pt[] } {
  const windows: Pt[] = [];
  const cols = Math.floor((w - 10) / 12);
  for (let r = 0; r < floors; r++) for (let c = 0; c < cols; c++) windows.push([x + 8 + c * 12, -9 - r * ((h - 12) / floors)]);
  return { shape: rect(x, w, h), windows };
}

function tree(x: number, r: number): Shape {
  return lib.ellipsePts(x, -r * 1.2, r, r * 1.1, 18);
}

const SCENES: Record<Scene, Piece[]> = {
  classic: [stalinka(250), spasskaya(760), shukhov(1190), ostankino(1640)],
  vdnh: [ostankino(1190), vdnhArch(1790)],
  city: [moscowCity(330), stalinka(1060), shukhov(1520)],
  luzhniki: [stalinka(980, 1.8), luzhniki(1520), ostankino(300)],
  kremlin: [kremlinWall(0, 330), spasskaya(165, true), kremlinWall(620, 1300), basil(1765)],
  theatre: [bolshoi(320), shukhov(1250), stalinka(1700)],
  bridge: [krymsky(1570), stalinka(760), moscowCity(1180)],
  panorama: [kremlinWall(0, 320), spasskaya(160, true), stalinka(640, 1.4), luzhniki(1080), ostankino(1440), moscowCity(1730)],
};

function extent(p: Piece): [number, number] {
  const xs = [...(p.shapes ?? []), ...(p.colored ?? []).map((c) => c.shape)].flat().map(([x]) => x);
  return [Math.min(...xs), Math.max(...xs)];
}

/** Панорама места: достопримечательности, между ними дома и деревья. */
export function skyline(scene: Scene, seed: number): Skyline {
  const r = lib.rng(`sky${scene}${seed}`);
  const s: Skyline = { back: [], front: [], colored: [], windows: [], stars: [], lattice: [], trees: [] };
  const pieces = SCENES[scene];
  for (const p of pieces) {
    s.back.push(...(p.shapes ?? []));
    s.colored.push(...(p.colored ?? []));
    s.windows.push(...(p.windows ?? []));
    s.stars.push(...(p.stars ?? []));
    s.lattice.push(...(p.lattice ?? []));
  }
  const taken = pieces.map(extent);
  for (let x = -20; x < 1940;) {
    const w = r.range(70, 150);
    const h = r.range(32, 64);
    if (!taken.some(([a, b]) => x + w > a - 16 && x < b + 16)) {
      const home = house(x, w, h, Math.round(h / 12));
      s.front.push(home.shape);
      s.windows.push(...home.windows);
    }
    x += w + r.range(20, 60);
  }
  for (let k = 0; k < 16; k++) s.trees.push(tree(r.range(0, 1920), r.range(9, 15)));
  return s;
}
