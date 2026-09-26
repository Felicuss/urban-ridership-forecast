import { create } from 'zustand';

// Сессия диспетчера. Сервис выдаёт её HttpOnly-cookie: скрипты страницы токен не видят, браузер сам
// отправляет cookie с каждым запросом к /api. Если сессия истекла, любой ответ 401 возвращает экран входа.
// Модуль импортируется первым в main.tsx: перехват fetch должен стоять до создания клиента API.

export interface SessionUser {
  username: string;
  name: string;
  authRequired: boolean;
}

type Status = 'checking' | 'anon' | 'in';

interface SessionState {
  status: Status;
  user: SessionUser | null;
  signedIn: (user: SessionUser) => void;
  signedOut: () => void;
}

export const useSession = create<SessionState>((set) => ({
  status: 'checking',
  user: null,
  signedIn: (user) => set({ status: 'in', user }),
  signedOut: () => set({ status: 'anon', user: null }),
}));

const AUTH_PATH = '/api/v1/auth/';

const nativeFetch = window.fetch.bind(window);

// ответ 401 на запрос к API вне входа значит, что сессия кончилась: показываем экран входа
window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const response = await nativeFetch(input, init);
  const url = typeof input === 'string' ? input : input instanceof URL ? input.pathname : input.url;
  if (response.status === 401 && url.includes('/api/') && !url.includes(AUTH_PATH)
    && useSession.getState().status === 'in') {
    useSession.getState().signedOut();
  }
  return response;
};

interface Problem {
  detail?: string;
  title?: string;
}

async function problemText(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.json()) as Problem;
    return body.detail ?? body.title ?? fallback;
  } catch {
    return fallback;
  }
}

/** Кто вошёл; null - сессии нет. Ошибка сети пробрасывается: её показывает экран входа. */
export async function currentUser(): Promise<SessionUser | null> {
  const res = await nativeFetch(`${AUTH_PATH}me`);
  if (res.status === 401) return null;
  if (!res.ok) throw new Error(await problemText(res, `Сервис ответил ${res.status}`));
  return (await res.json()) as SessionUser;
}

export async function signIn(username: string, password: string): Promise<SessionUser> {
  const res = await nativeFetch(`${AUTH_PATH}login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error(await problemText(res, `Сервис ответил ${res.status}`));
  return (await res.json()) as SessionUser;
}

export async function signOut(): Promise<void> {
  await nativeFetch(`${AUTH_PATH}logout`, { method: 'POST' }).catch(() => null);
  useSession.getState().signedOut();
}
