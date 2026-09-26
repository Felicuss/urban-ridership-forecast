// Типы той части lib.js (procedural-film, MIT), которой пользуются слайды.

export type Pt = [number, number];
type Ctx = CanvasRenderingContext2D;
export type EaseName =
  | 'linear' | 'inQuad' | 'outQuad' | 'inOutQuad' | 'inCubic' | 'outCubic' | 'inOutCubic' | 'inQuart' | 'outQuart'
  | 'inOutQuart' | 'inQuint' | 'outQuint' | 'inOutQuint' | 'inSine' | 'outSine' | 'inOutSine' | 'inExpo' | 'outExpo'
  | 'inOutExpo' | 'inCirc' | 'outCirc' | 'inOutCirc' | 'inBack' | 'outBack' | 'inOutBack' | 'outElastic' | 'outBounce';

export interface InkOpts {
  closed?: boolean;
  width?: number;
  color?: string;
  alpha?: number;
  seed?: number | string;
  wobble?: number;
  tremble?: number;
  boil?: boolean;
  boilAmp?: number;
  taper?: number | [number, number];
  fill?: string;
  fillAlpha?: number;
  smooth?: boolean;
  double?: boolean;
  widthJitter?: number;
  step?: number;
  ry?: number;
}

export interface Rng {
  (): number;
  range(lo: number, hi: number): number;
  int(lo: number, hi: number): number;
}

export interface FilmLib {
  readonly T: number;
  clamp(v: number, lo?: number, hi?: number): number;
  lerp(a: number, b: number, t: number): number;
  smoothstep(e0: number, e1: number, x: number): number;
  seg(t: number, t0: number, t1: number, e?: EaseName): number;
  ease: Record<EaseName, (p: number) => number>;
  pal: Record<string, string>;
  rgba(c: string, a?: number): string;
  mix(a: string, b: string, t: number): string;
  rng(seed: string | number): Rng;
  noise1(x: number, seed: number): number;
  onTwos(t: number): number;
  inkPath(ctx: Ctx, pts: Pt[], o?: InkOpts): void;
  inkLine(ctx: Ctx, x1: number, y1: number, x2: number, y2: number, o?: InkOpts): void;
  inkCircle(ctx: Ctx, cx: number, cy: number, r: number, o?: InkOpts): void;
  ellipsePts(cx: number, cy: number, rx: number, ry?: number, n?: number, rot?: number): Pt[];
  rectPts(x: number, y: number, w: number, h: number, step?: number): Pt[];
  rrectPts(x: number, y: number, w: number, h: number, r: number, step?: number): Pt[];
  smoothPts(pts: Pt[], closed?: boolean, step?: number): Pt[];
  tracePath(ctx: Ctx, pts: Pt[], closed?: boolean): void;
  hatch(ctx: Ctx, clip: Pt[] | null, o?: Record<string, unknown>): void;
  stipple(ctx: Ctx, clip: Pt[] | null, o?: Record<string, unknown>): void;
  paper(ctx: Ctx, o?: Record<string, unknown>): void;
  blueprint(ctx: Ctx, o?: Record<string, unknown>): void;
  stripes(ctx: Ctx, o?: Record<string, unknown>): void;
  glowDot(ctx: Ctx, x: number, y: number, r: number, o?: Record<string, unknown>): void;
  ticks(ctx: Ctx, x: number, y: number, o?: Record<string, unknown>): void;
  bracket(ctx: Ctx, x1: number, y1: number, x2: number, y2: number, o?: Record<string, unknown>): void;
  guideCircle(ctx: Ctx, cx: number, cy: number, r: number, o?: Record<string, unknown>): void;
}

export interface Film {
  W: number;
  H: number;
  S: number;
  frameT: number;
  lib: FilmLib;
  makeCanvas(w: number, h: number): HTMLCanvasElement;
}
