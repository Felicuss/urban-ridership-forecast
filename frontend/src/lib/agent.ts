// Клиент агента: вопрос уходит POST /api/v1/agent/chat, ответ приходит потоком SSE событий step, ui,
// answer и error. Сессия диалога живёт в браузере, история для модели хранится на сервере (Redis) сутки.

export interface AgentEvent {
  type: 'step' | 'ui' | 'answer' | 'error';
  text?: string | null;
  tool?: string | null;
  action?: UiAction | null;
}

export type UiAction =
  | { type: 'show'; network?: boolean; date?: string; hour?: number; route?: number; stop?: string; view?: 'top' | 'perspective';
    horizon?: 'day' | 'week' | 'month' | 'year'; tab?: 'forecast' | 'shift' | 'scenario' | 'factors' | 'model' }
  | { type: 'layers'; enable?: string[]; disable?: string[]; hideRoutes?: number[] }
  | { type: 'ride'; route: number; direction?: 0 | 1 };

export interface AgentStatus {
  configured: boolean;
  model: string;
  memory: string;
  memoryHealthy: boolean;
}

const SESSION_KEY = 'chaspik.agent.session';

/** Событие окна, по которому плашка агента открывается и сразу задаёт вопрос: так спрашивают из панелей. */
export const ASK_EVENT = 'chaspik:ask';

export function askFromUi(question: string): void {
  window.dispatchEvent(new CustomEvent<string>(ASK_EVENT, { detail: question }));
}

export function agentSession(): string {
  try {
    const known = localStorage.getItem(SESSION_KEY);
    if (known) return known;
    const fresh = crypto.randomUUID();
    localStorage.setItem(SESSION_KEY, fresh);
    return fresh;
  } catch {
    return 'volatile-' + Math.random().toString(36).slice(2, 12);
  }
}

export async function agentStatus(): Promise<AgentStatus | null> {
  const res = await fetch('/api/v1/agent/status').catch(() => null);
  return res?.ok ? ((await res.json()) as AgentStatus) : null;
}

export async function resetAgent(): Promise<void> {
  await fetch('/api/v1/agent/reset', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session: agentSession() }) }).catch(() => undefined);
}

/** Задать вопрос: onEvent получает события по мере прихода, промис завершается вместе с потоком. */
export async function askAgent(message: string, context: Record<string, unknown>, onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal): Promise<void> {
  const res = await fetch('/api/v1/agent/chat', {
    method: 'POST', signal,
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ session: agentSession(), message, context }),
  });
  if (!res.ok || !res.body) {
    const problem = (await res.json().catch(() => null)) as { detail?: string } | null;
    onEvent({ type: 'error', text: problem?.detail ?? `сервис ответил ${res.status}` });
    return;
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value.replace(/\r/g, '');
    let cut = buffer.indexOf('\n\n');
    while (cut >= 0) {
      const data = buffer.slice(0, cut).split('\n').filter((l) => l.startsWith('data:')).map((l) => l.slice(5)).join('');
      buffer = buffer.slice(cut + 2);
      if (data) onEvent(JSON.parse(data) as AgentEvent);
      cut = buffer.indexOf('\n\n');
    }
  }
}
