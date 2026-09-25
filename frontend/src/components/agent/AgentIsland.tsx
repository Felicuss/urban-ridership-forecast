import { useCallback, useEffect, useRef, useState } from 'react';
import { agentStatus, askAgent, resetAgent, type AgentStatus } from '../../lib/agent';
import { applyUiAction } from '../../state/uiActions';
import { useStore } from '../../state/store';
import { dayIndex, hourOf, isoDate } from '../../lib/time';
import { Icon } from '../ui/Icons';
import { useSpeech } from './useSpeech';
import styles from './AgentIsland.module.css';

// Помощник диспетчера в стиле Dynamic Island: свёрнутая плашка в верхней строке показывает, что агент делает
// сейчас («Считаю прогноз»), раскрытая - диалог, подсказки, ввод текстом или голосом. Команды агента
// (открыть дату, маршрут, слой, пустить трамвай) применяются к интерфейсу сразу.

interface Line {
  role: 'user' | 'agent' | 'error';
  text: string;
}

const EXAMPLES = [
  'Покажи 17 маршрут 14 ноября в 8 утра',
  'Где на этой неделе рейсы переполнены?',
  'Сравни посадки 7 и 17 маршрута за ноябрь',
  'Что будет, если перекрыть 17 маршрут в субботу днём?',
];

export function AgentIsland() {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<AgentStatus | null | undefined>(undefined);
  const [lines, setLines] = useState<Line[]>([]);
  const [steps, setSteps] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState('');
  const abort = useRef<AbortController | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const log = useRef<HTMLDivElement>(null);

  const send = useCallback(async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    const s = useStore.getState();
    const context = { date: isoDate(dayIndex(s.minute)), hour: hourOf(s.minute), route: s.route, stop: s.stop,
      view: s.viewMode, tab: s.tab, horizon: s.horizon };
    setDraft('');
    setOpen(true);
    setBusy(true);
    setSteps([]);
    setLines((l) => [...l, { role: 'user', text: question }]);
    abort.current = new AbortController();
    try {
      await askAgent(question, context, (e) => {
        if (e.type === 'step' && e.text) setSteps((st) => [...st, e.text!]);
        if (e.type === 'ui' && e.action) applyUiAction(e.action);
        if (e.type === 'answer' && e.text) setLines((l) => [...l, { role: 'agent', text: e.text! }]);
        if (e.type === 'error' && e.text) setLines((l) => [...l, { role: 'error', text: e.text! }]);
      }, abort.current.signal);
    } catch (err) {
      if (!(err instanceof DOMException && err.name === 'AbortError')) {
        setLines((l) => [...l, { role: 'error', text: 'Сервис агента недоступен: проверьте соединение.' }]);
      }
    } finally {
      setBusy(false);
      setSteps([]);
    }
  }, [busy]);

  const speech = useSpeech((heard, final) => {
    setDraft(heard);
    if (final) void send(heard);
  });

  useEffect(() => {
    if (open && status === undefined) void agentStatus().then(setStatus);
    if (open) input.current?.focus();
  }, [open, status]);

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight, behavior: 'smooth' });
  }, [lines, steps]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement;
      if ((e.key === '/' && !typing) || (e.key === 'k' && (e.ctrlKey || e.metaKey))) {
        e.preventDefault();
        setOpen(true);
      }
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', key);
    return () => document.removeEventListener('keydown', key);
  }, []);

  const live = busy ? steps.at(-1) ?? 'Думаю…' : null;
  const notReady = status && !status.configured;

  return (
    <div className={`${styles.island} ${open ? styles.open : ''} ${busy ? styles.busy : ''}`}>
      <button type="button" className={styles.pill} onClick={() => setOpen((v) => !v)} aria-expanded={open}
        title="Помощник диспетчера: вопрос словами или голосом, клавиша /">
        <span className={styles.orb} aria-hidden="true" />
        <span className={styles.pillText}>{live ?? 'Спросить «Час пик»'}</span>
        {!busy && <kbd>/</kbd>}
      </button>
      {open && (
        <div className={styles.panel} role="dialog" aria-label="Помощник диспетчера">
          <header>
            <b>Помощник диспетчера</b>
            <small>{status === undefined ? 'проверяю…' : notReady ? 'не настроен: нет ключа модели'
              : status ? `${status.model}, память ${status.memory === 'redis' ? 'Redis' : 'в процессе'}` : 'сервис недоступен'}</small>
            <button type="button" title="Начать диалог заново" onClick={() => { setLines([]); void resetAgent(); }}>
              <Icon.reset /></button>
            <button type="button" aria-label="Свернуть" onClick={() => setOpen(false)}><Icon.close /></button>
          </header>
          <div ref={log} className={styles.log} aria-live="polite">
            {lines.length === 0 && (
              <div className={styles.examples}>
                <p>Спросите словами: агент посчитает, покажет на карте и откроет нужную панель.</p>
                {EXAMPLES.map((x) => <button key={x} type="button" onClick={() => void send(x)}>{x}</button>)}
              </div>
            )}
            {lines.map((l, i) => <p key={i} className={styles[l.role]}>{l.text}</p>)}
            {busy && <p className={styles.steps}>{steps.length ? steps.join(' → ') : 'Думаю…'}</p>}
          </div>
          <form className={styles.input} onSubmit={(e) => { e.preventDefault(); void send(draft); }}>
            <input ref={input} value={draft} maxLength={1000} placeholder={speech.listening ? 'Слушаю…' : 'Вопрос о посадках'}
              onChange={(e) => setDraft(e.target.value)} aria-label="Вопрос агенту" disabled={busy} />
            {speech.supported && (
              <button type="button" className={speech.listening ? styles.micOn : styles.mic} disabled={busy}
                onClick={speech.listening ? speech.stop : speech.start}
                aria-label={speech.listening ? 'Остановить запись' : 'Спросить голосом'} title="Голосовой ввод, русский">
                <Icon.mic /></button>
            )}
            {busy
              ? <button type="button" className={styles.send} onClick={() => abort.current?.abort()}>Стоп</button>
              : <button type="submit" className={styles.send} disabled={!draft.trim()}>Спросить</button>}
          </form>
        </div>
      )}
    </div>
  );
}
