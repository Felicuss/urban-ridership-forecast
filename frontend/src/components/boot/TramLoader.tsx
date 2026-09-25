import styles from './TramLoader.module.css';

export interface LoadStep {
  label: string;
  done: boolean;
}

/**
 * Загрузочный экран: трамвай в цветах «Витязя-М» едет под контактным проводом, пока грузятся
 * данные и карта. Шаги внизу - настоящие запросы, а не таймер.
 */
export function TramLoader({ steps, leaving }: { steps: LoadStep[]; leaving: boolean }) {
  const done = steps.filter((s) => s.done).length;
  const pct = Math.round((100 * done) / Math.max(steps.length, 1));
  return (
    <div className={`${styles.root} ${leaving ? styles.leaving : ''}`} role="status" aria-live="polite">
      <div className={styles.scene}>
        <svg className={styles.city} viewBox="0 0 800 120" preserveAspectRatio="none" aria-hidden="true">
          <path d="M0 120V70h40V40h30v30h20V55h35v65M150 120V60h25V30h40v90M230 120V75h30V50h20v70M300 120V35h45v85M360 120V65h30V45h25v75M430 120V55h40V25h30v95M520 120V70h35V50h30v70M600 120V40h40v80M660 120V60h30V35h35v85M740 120V70h60v50" />
        </svg>
        <svg className={styles.tram} viewBox="0 0 440 150" aria-hidden="true">
          <line x1="-40" y1="14" x2="480" y2="14" className={styles.wire} />
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
