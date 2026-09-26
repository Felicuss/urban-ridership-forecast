import type { Sky } from '../../lib/weather';

// Иконки интерфейса одним набором линий 1.6 px, чтобы не тянуть библиотеку ради пары десятков глифов.
const base = { width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.7,
  strokeLinecap: 'round', strokeLinejoin: 'round' } as const;

export const Icon = {
  play: () => <svg {...base}><path d="M7 5l12 7-12 7z" fill="currentColor" /></svg>,
  pause: () => <svg {...base}><path d="M8 5v14M16 5v14" strokeWidth="2.6" /></svg>,
  prev: () => <svg {...base}><path d="M15 6l-6 6 6 6" /></svg>,
  next: () => <svg {...base}><path d="M9 6l6 6-6 6" /></svg>,
  gear: () => <svg {...base}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h.1a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v.1a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></svg>,
  download: () => <svg {...base}><path d="M12 4v11M7 10l5 5 5-5M5 20h14" /></svg>,
  close: () => <svg {...base}><path d="M6 6l12 12M18 6L6 18" /></svg>,
  help: () => <svg {...base}><circle cx="12" cy="12" r="9" /><path d="M9.6 9.3a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.2-2.4 3.8" /><path d="M12 17.2v.1" strokeWidth="2.4" /></svg>,
  now: () => <svg {...base}><circle cx="12" cy="12" r="8" /><path d="M12 8v4l3 2" /></svg>,
  tram: () => <svg {...base}><rect x="6" y="5" width="12" height="13" rx="3" /><path d="M6 13h12M9 21l1-3M15 21l-1-3M10 2h4M12 2v3" /></svg>,
  layers: () => <svg {...base}><path d="M12 3l9 5-9 5-9-5z" /><path d="M3 13l9 5 9-5" /></svg>,
  external: () => <svg {...base}><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></svg>,
  reset: () => <svg {...base}><path d="M4 12a8 8 0 1 0 3-6.2M4 4v5h5" /></svg>,
  calendar: () => <svg {...base}><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M4 10h16M9 3v4M15 3v4" /></svg>,
  mic: () => <svg {...base}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>,
  board: () => <svg {...base}><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8M12 17v4" /></svg>,
  bell: () => <svg {...base}><path d="M6 16V11a6 6 0 1 1 12 0v5l2 2H4z" /><path d="M10 20a2 2 0 0 0 4 0" /></svg>,
};

export function SkyIcon({ sky, night }: { sky: Sky; night: boolean }) {
  const sun = night
    ? <path d="M15.5 4.5a7 7 0 1 0 4 12.5 8 8 0 0 1-4-12.5z" fill="#c9d6ff" stroke="none" />
    : <><circle cx="12" cy="12" r="4.5" fill="#ffd166" stroke="none" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5" stroke="#ffd166" /></>;
  const cloud = <path d="M7 18h10a4 4 0 0 0 .6-8A6 6 0 0 0 6.2 11 3.5 3.5 0 0 0 7 18z" fill="#9fb1c8" stroke="none" />;
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
      {sky === 'clear' && sun}
      {sky !== 'clear' && cloud}
      {sky === 'rain' && <path d="M9 20l-1 2M13 20l-1 2M17 20l-1 2" stroke="#7cc0ff" />}
      {sky === 'snow' && <path d="M9 21h.01M13 22h.01M17 21h.01" stroke="#ffffff" strokeWidth="2.6" />}
      {sky === 'storm' && <path d="M12 18l-2 4h3l-1 2" stroke="#ffd166" />}
      {sky === 'fog' && <path d="M5 21h14" stroke="#9fb1c8" />}
    </svg>
  );
}
