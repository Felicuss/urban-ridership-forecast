import { useId, type ReactNode } from 'react';
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
export function InfoTip({ children }: { children: ReactNode }) {
  return (
    <span className={styles.info} tabIndex={0} aria-label="Пояснение">
      ?
      <span className={styles.infoBody} role="tooltip">{children}</span>
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

export function Card({ title, info, actions, children, className }: {
  title?: ReactNode;
  info?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`${styles.card} ${className ?? ''}`}>
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
