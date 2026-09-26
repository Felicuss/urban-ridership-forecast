import { useEffect } from 'react';
import { signOut, useSession } from '../../api/session';
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
  const user = useSession((s) => s.user);
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
        {user?.authRequired && (
          <section className={styles.account}>
            <div>
              <b>{user.name}</b>
              <small>вход: {user.username}</small>
            </div>
            <button type="button" onClick={() => void signOut()}>Выйти</button>
          </section>
        )}
        {GROUPS.map((g) => (
          <section key={g.title}>
            <h3>{g.title}</h3>
            {g.keys.map((k) => (
              <Toggle key={k} checked={flags[k]} onChange={(v) => setFlag(k, v)} label={FLAG_LABELS[k].label}
                hint={FLAG_LABELS[k].hint} />
            ))}
          </section>
        ))}
        <section>
          <h3>Клавиши</h3>
          <dl className={styles.keys}>
            <dt>1 7</dt><dd>маршрут 17: номер набирается цифрами подряд, 0 - вся сеть</dd>
            <dt>S</dt><dd>маршрут по станциям и дням</dd>
            <dt>Shift + ← →</dt><dd>день назад и вперёд (в матрице станций без Shift)</dd>
            <dt>Shift + ↑ ↓</dt><dd>час назад и вперёд</dd>
            <dt>/</dt><dd>спросить помощника</dd>
            <dt>Esc</dt><dd>закрыть панель или снять выбор маршрута</dd>
            <dt>?</dt><dd>эти настройки и список клавиш</dd>
          </dl>
        </section>
        <p>Выбор хранится в этом браузере. Без анимаций и погоды интерфейс легче для слабых машин.</p>
      </div>
    </div>
  );
}
