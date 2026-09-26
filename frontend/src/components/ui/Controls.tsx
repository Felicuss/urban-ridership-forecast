import { useId, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import styles from './Controls.module.css';

export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T;
  options: { value: T; label: string; hint?: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className={styles.segmented} role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          title={o.hint}
          className={o.value === value ? styles.segActive : styles.seg}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Toggle({ checked, onChange, label, hint }: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: string;
}) {
  const id = useId();
  return (
    <label className={styles.toggle} htmlFor={id} title={hint}>
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className={styles.track} aria-hidden="true"><span className={styles.thumb} /></span>
      <span className={styles.toggleText}>
        {label}
        {hint && <small>{hint}</small>}
      </span>
    </label>
  );
}

/** Значок «?» с объяснением: что значит показатель и откуда он. */
const TIP_WIDTH = 280;
const TIP_MARGIN = 10;
/** Если снизу меньше места, подсказка открывается вверх. */
const TIP_ROOM = 180;

interface TipPlace {
  left: number;
  top: number;
  width: number;
  above: boolean;
}

/**
 * Пояснение по наведению или фокусу. Рисуется поверх страницы в портале, поэтому его не обрезают
 * панели с прокруткой, и прижимается к краям экрана: влезает и у правого края, и на телефоне.
 */
export function InfoTip({ children }: { children: ReactNode }) {
  const icon = useRef<HTMLSpanElement>(null);
  const id = useId();
  const [place, setPlace] = useState<TipPlace | null>(null);
  const show = () => {
    const r = icon.current?.getBoundingClientRect();
    if (!r) return;
    const width = Math.min(TIP_WIDTH, window.innerWidth - 2 * TIP_MARGIN);
    const left = Math.min(Math.max(r.left + r.width / 2 - width / 2, TIP_MARGIN), window.innerWidth - width - TIP_MARGIN);
    const below = window.innerHeight - r.bottom;
    const above = below < TIP_ROOM && r.top > below;
    setPlace({ left, width, above, top: above ? r.top - 8 : r.bottom + 8 });
  };
  const hide = () => setPlace(null);
  return (
    <span ref={icon} className={styles.info} tabIndex={0} aria-label="Пояснение" aria-describedby={place ? id : undefined}
      onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}>
      ?
      {place && createPortal(
        <span id={id} className={styles.infoBody} role="tooltip"
          style={{ left: place.left, top: place.top, width: place.width,
            transform: place.above ? 'translateY(-100%)' : undefined }}>
          {children}
        </span>,
        document.body,
      )}
    </span>
  );
}

export function Kpi({ label, value, sub, info, tone }: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  info?: ReactNode;
  tone?: 'up' | 'down' | 'accent';
}) {
  return (
    <div className={styles.kpi}>
      <div className={styles.kpiLabel}>
        {label}
        {info && <InfoTip>{info}</InfoTip>}
      </div>
      <div className={`${styles.kpiValue} num ${tone ? styles[tone] : ''}`}>{value}</div>
      {sub && <div className={styles.kpiSub}>{sub}</div>}
    </div>
  );
}

export function Card({ title, info, actions, children, className, id }: {
  title?: ReactNode;
  info?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={`${styles.card} ${className ?? ''}`}>
      {(title || actions) && (
        <header className={styles.cardHead}>
          <h3>
            {title}
            {info && <InfoTip>{info}</InfoTip>}
          </h3>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

/** Мини-лоадер: вагон бежит по рельсу, пока грузится блок. */
export function TramDots({ label = 'Считаем' }: { label?: string }) {
  return (
    <div className={styles.dots} role="status">
      <span className={styles.rail}><span className={styles.car} /></span>
      {label}
    </div>
  );
}
