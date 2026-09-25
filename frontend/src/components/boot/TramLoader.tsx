import styles from './TramLoader.module.css';

export interface LoadStep {
  label: string;
  done: boolean;
}

/** Сколько длится уход: трамвай разгоняется и уезжает за край, экран гаснет над картой. */
export const LEAVE_MS = 1400;

/** Силуэт сталинской высотки (по мотивам главного здания МГУ): ярусы, шпиль, боковые башни. */
const TOWER = 'M40 230V185H70V150H100V185H130V150H150V112H165V82H178V58H188V40H196L200 6L204 40H212V58H222V82'
  + 'H235V112H250V150H270V185H300V150H330V185H360V230Z M83 150L85 128L87 150Z M313 150L315 128L317 150Z';
const STAR = 'M200 -2L201.4 2.1L205.7 2.2L202.3 4.7L203.5 8.9L200 6.4L196.5 8.9L197.7 4.7L194.3 2.2L198.6 2.1Z';

/** Окна ярусов: светится примерно каждое пятое, узор постоянный. */
const TIERS: { x0: number; x1: number; y0: number; y1: number }[] = [
  { x0: 136, x1: 264, y0: 158, y1: 222 },
  { x0: 154, x1: 246, y0: 118, y1: 146 },
  { x0: 169, x1: 231, y0: 88, y1: 108 },
  { x0: 181, x1: 219, y0: 63, y1: 78 },
  { x0: 46, x1: 124, y0: 192, y1: 222 },
  { x0: 276, x1: 354, y0: 192, y1: 222 },
];
const WINDOWS = TIERS.flatMap((t, ti) => {
  const out: { x: number; y: number }[] = [];
  for (let y = t.y0, row = 0; y <= t.y1; y += 10, row++) {
    for (let x = t.x0, col = 0; x <= t.x1; x += 8, col++) {
      if ((row * 7 + col * 3 + ti) % 5 === 0) out.push({ x, y });
    }
  }
  return out;
});

/**
 * Загрузочный экран: трамвай в цветах «Витязя-М» едет под контактным проводом, пока грузятся
 * данные и карта, на фоне сталинской высотки. Шаги внизу - настоящие запросы, а не таймер.
 * Когда всё готово (leaving), трамвай разгоняется и уезжает за край, а экран гаснет над картой.
 */
export function TramLoader({ steps, leaving }: { steps: LoadStep[]; leaving: boolean }) {
  const done = steps.filter((s) => s.done).length;
  const pct = Math.round((100 * done) / Math.max(steps.length, 1));
  return (
    <div className={`${styles.root} ${leaving ? styles.leaving : ''}`} role="status" aria-live="polite">
      <div className={styles.scene}>
        <svg className={styles.skyline} viewBox="0 -6 400 236" aria-hidden="true">
          <defs>
            <linearGradient id="tower-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#9fb2d0" stopOpacity="0.24" />
              <stop offset="1" stopColor="#9fb2d0" stopOpacity="0.06" />
            </linearGradient>
          </defs>
          <path d={TOWER} fill="url(#tower-fill)" />
          {WINDOWS.map((w) => <rect key={`${w.x}-${w.y}`} className={styles.lit} x={w.x} y={w.y} width="2.4" height="3.4" />)}
          <path className={styles.star} d={STAR} />
        </svg>
        <svg className={styles.city} viewBox="0 0 800 120" preserveAspectRatio="none" aria-hidden="true">
          <path d="M0 120V70h40V40h30v30h20V55h35v65M150 120V60h25V30h40v90M230 120V75h30V50h20v70M300 120V35h45v85M360 120V65h30V45h25v75M430 120V55h40V25h30v95M520 120V70h35V50h30v70M600 120V40h40v80M660 120V60h30V35h35v85M740 120V70h60v50" />
        </svg>
        <svg className={styles.tram} viewBox="0 0 440 150" aria-hidden="true">
          <line x1="-40" y1="14" x2="480" y2="14" className={styles.wire} />
          <g className={styles.car}>
          <g className={styles.body}>
            <path className={styles.pantograph} d="M232 42 L214 26 L236 16 M214 26 L246 16" />
            <circle className={styles.spark} cx="241" cy="15" r="4" />
            <path className={styles.roof} d="M40 44 h300 q18 0 24 10 h-348 q6 -10 24 -10z" />
            <path className={styles.shell} d="M22 54 h348 q28 0 44 30 l6 26 q2 12 -10 12 H22 q-10 0 -10 -10 V64 q0 -10 10 -10z" />
            <path className={styles.mask} d="M372 56 q24 2 38 30 l7 24 q1 8 -8 8 h-26 z" />
            <path className={styles.glass} d="M378 62 q18 4 28 26 l2 8 h-30 z" />
            <path className={styles.skirt} d="M12 104 H414 l2 6 q2 12 -10 12 H22 q-10 0 -10 -10z" />
            <path className={styles.wave} d="M30 62 q8 -6 16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0" />
            {[36, 92, 150, 250, 306].map((x) => (
              <rect key={x} className={styles.window} x={x} y="70" width="44" height="26" rx="4" />
            ))}
            {[196, 356].map((x) => (
              <g key={x}>
                <rect className={styles.door} x={x} y="66" width="34" height="50" rx="3" />
                <line className={styles.doorLine} x1={x + 17} y1="68" x2={x + 17} y2="114" />
              </g>
            ))}
            <circle className={styles.logo} cx="240" cy="84" r="7" />
            <path className={styles.logoMark} d="M237 87 v-5 a3 3 0 0 1 6 0 v5" />
            <text className={styles.number} x="300" y="117">30636</text>
            <circle className={styles.headlight} cx="408" cy="108" r="3.5" />
            <path className={styles.beam} d="M411 108 L470 96 L470 122 Z" />
          </g>
          {[70, 118, 300, 348].map((x) => (
            <g key={x} className={styles.wheel} style={{ transformOrigin: `${x}px 126px` }}>
              <circle cx={x} cy="126" r="11" />
              <line x1={x - 8} y1="126" x2={x + 8} y2="126" />
            </g>
          ))}
          </g>
          <line x1="-40" y1="138" x2="480" y2="138" className={styles.rail} />
          <line x1="-40" y1="144" x2="480" y2="144" className={styles.sleepers} />
        </svg>
      </div>
      <div className={styles.caption}>
        <div className={styles.title}>Трамвай. Прогноз посадок</div>
        <div className={styles.track}>
          <div className={styles.progress} style={{ width: `${pct}%` }} />
        </div>
        <ul className={styles.steps}>
          {steps.map((s) => (
            <li key={s.label} className={s.done ? styles.done : ''}>
              <span className={styles.dot} />
              {s.label}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
