import { useCallback, useEffect, useRef, useState } from 'react';
import { ASK_EVENT, agentStatus, askAgent, resetAgent, type AgentStatus } from '../../lib/agent';
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

/** Что умеет помощник: коротко, словами диспетчера. */
const SKILLS = [
  'считает посадки по маршруту, остановке или всей сети на час, день, неделю, месяц',
  'находит часы, где на рейс входит больше людей, чем помещается в вагон, и советует интервал',
  'сравнивает маршруты и даты между собой',
  'примеряет перекрытие, мероприятие или снегопад и говорит, сколько пассажиров потеряем',
  'сам открывает нужную дату, маршрут и панель на карте',
];

const EXAMPLES = [
  'Покажи 17 маршрут 14 ноября в 8 утра',
  'Где на этой неделе рейсы переполнены?',
  'Сравни посадки 7 и 17 маршрута за ноябрь',
  'Что будет, если перекрыть 17 маршрут в субботу днём?',
  'Какой пиковый час у 26 маршрута в понедельник?',
];

export function AgentIsland() {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<AgentStatus | null | undefined>(undefined);
  const [lines, setLines] = useState<Line[]>([]);
  const [steps, setSteps] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState('');
  const [help, setHelp] = useState(false);
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
    setHelp(false);
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

  // вопрос из панели (например, «пересказать сводку смены») открывает плашку и уходит агенту
  useEffect(() => {
    const ask = (e: Event) => {
      const text = (e as CustomEvent<string>).detail;
      if (typeof text === 'string') void send(text);
    };
    window.addEventListener(ASK_EVENT, ask);
    return () => window.removeEventListener(ASK_EVENT, ask);
  }, [send]);

  const openRef = useRef(open);
  useEffect(() => {
    openRef.current = open;
  }, [open]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement;
      // в русской раскладке на клавише «/» точка, а Ctrl+K даёт «л»: смотрим и на физическую клавишу
      const slash = e.key === '/' || (e.code === 'Slash' && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey);
      if ((slash && !typing) || ((e.key === 'k' || e.code === 'KeyK') && (e.ctrlKey || e.metaKey))) {
        e.preventDefault();
        setOpen(true);
      }
      if (e.key === 'Escape' && openRef.current) {
        // Esc закрывает помощника, а выбор маршрута не снимает
        e.preventDefault();
        setOpen(false);
      }
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
        <span className={styles.pillText}>{live ?? <>Спросить<span className={styles.pillName}> «Час пик»</span></>}</span>
        {!busy && <kbd>/</kbd>}
      </button>
      {open && (
        <div className={styles.panel} role="dialog" aria-label="Помощник диспетчера">
          <header>
            <b>Помощник диспетчера</b>
            <small title={status ? `модель ${status.model}, память ${status.memory}` : undefined}>
              {status === undefined ? 'проверяю…' : notReady ? 'не настроен: нет ключа модели' : status ? 'на связи' : 'сервис недоступен'}
            </small>
            <button type="button" title="Что умеет помощник и примеры вопросов" aria-pressed={help}
              onClick={() => setHelp((v) => !v)}><Icon.help /></button>
            <button type="button" title="Начать диалог заново" onClick={() => { setLines([]); void resetAgent(); }}>
              <Icon.reset /></button>
            <button type="button" aria-label="Свернуть" onClick={() => setOpen(false)}><Icon.close /></button>
          </header>
          <div ref={log} className={styles.log} aria-live="polite">
            {(lines.length === 0 || help) && (
              <div className={styles.examples}>
                <p>Спросите словами или голосом (кнопка с микрофоном). Помощник отвечает по прогнозу сервиса:</p>
                <ul className={styles.skills}>{SKILLS.map((x) => <li key={x}>{x}</li>)}</ul>
                <p>Нажмите на пример, чтобы спросить:</p>
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
