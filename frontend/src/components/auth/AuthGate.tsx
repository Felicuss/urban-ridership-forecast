import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { currentUser, signIn, useSession } from '../../api/session';
import styles from './AuthGate.module.css';

/**
 * Интерфейс открывается после входа. При запуске проверяем сессию; нет её - экран входа. После выхода или
 * истечения сессии кэш запросов очищается, чтобы следующий пользователь не увидел чужой сценарий.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const status = useSession((s) => s.status);
  const signedIn = useSession((s) => s.signedIn);
  const signedOut = useSession((s) => s.signedOut);
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    currentUser()
      .then((user) => {
        if (!alive) return;
        if (user) signedIn(user);
        else signedOut();
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setError(e instanceof Error ? e.message : 'Сервис прогноза не отвечает');
        signedOut();
      });
    return () => { alive = false; };
  }, [signedIn, signedOut]);

  useEffect(() => {
    if (status === 'anon') client.clear();
  }, [status, client]);

  if (status === 'checking') return null;
  if (status === 'anon') return <LoginScreen initialError={error} />;
  return <>{children}</>;
}

function LoginScreen({ initialError }: { initialError: string | null }) {
  const signedIn = useSession((s) => s.signedIn);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(initialError);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('Введите логин и пароль');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      signedIn(await signIn(username.trim(), password));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Вход не выполнен');
      setPassword('');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className={styles.screen}>
      <form className={styles.card} onSubmit={(e) => void submit(e)} aria-label="Вход в «Час пик»">
        <div className={styles.brand}>
          <span className={styles.logo} aria-hidden="true" />
          <div>
            <h1>Час пик</h1>
            <p>Прогноз посадок в трамваи Москвы для диспетчера</p>
          </div>
        </div>
        <label className={styles.field}>
          <span>Логин</span>
          <input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)}
            disabled={busy} />
        </label>
        <label className={styles.field}>
          <span>Пароль</span>
          <input type="password" autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} disabled={busy} />
        </label>
        {error && <p className={styles.error} role="alert">{error}</p>}
        <button type="submit" className={styles.submit} disabled={busy}>{busy ? 'Входим…' : 'Войти'}</button>
        <p className={styles.note}>Вход действует 12 часов. Учётные записи задаёт администратор сервиса.</p>
      </form>
    </main>
  );
}
