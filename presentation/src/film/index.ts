import './runtime';
import './lib.js';
import type { Film, FilmLib } from './lib.d';

// Движок рисования LCT_2026: сначала глобальные настройки, потом библиотека, которая к ним цепляется.

export const FILM = (window as unknown as { FILM: Film }).FILM;
export const lib: FilmLib = FILM.lib;
export const P = lib.pal;
export const E = lib.ease;
export type { Pt, InkOpts, EaseName } from './lib.d';
