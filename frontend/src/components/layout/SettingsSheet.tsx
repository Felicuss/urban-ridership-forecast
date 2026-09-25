import { useEffect } from 'react';
import { FLAG_LABELS, useStore, type Flags } from '../../state/store';
import { Toggle } from '../ui/Controls';
import { Icon } from '../ui/Icons';
import styles from './SettingsSheet.module.css';

const GROUPS: { title: string; keys: (keyof Flags)[] }[] = [
  { title: 'Слои карты', keys: ['heat', 'lines', 'stops', 'trams', 'metro', 'buildings', 'satellite', 'labels'] },
  { title: 'Окружение', keys: ['weather', 'daylight'] },
  { title: 'Интерфейс', keys: ['motion', 'intro'] },
];

/** Все флаги в одном месте: каждый слой и эффект можно выключить, выбор сохраняется в браузере. */
export function SettingsSheet({ onClose }: { onClose: () => void }) {
  const flags = useStore((s) => s.flags);
  const setFlag = useStore((s) => s.setFlag);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', esc);
    return () => document.removeEventListener('keydown', esc);
  }, [onClose]);

  return (
    <div className={styles.backdrop} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.sheet} role="dialog" aria-label="Настройки отображения">
        <header>
          <h2>Настройки</h2>
          <button type="button" aria-label="Закрыть" onClick={onClose}><Icon.close /></button>
        </header>
        {GROUPS.map((g) => (
          <section key={g.title}>
            <h3>{g.title}</h3>
            {g.keys.map((k) => (
              <Toggle key={k} checked={flags[k]} onChange={(v) => setFlag(k, v)} label={FLAG_LABELS[k].label}
                hint={FLAG_LABELS[k].hint} />
            ))}
          </section>
        ))}
        <p>Выбор хранится в этом браузере. Без анимаций и погоды интерфейс легче для слабых машин.</p>
      </div>
    </div>
  );
}
