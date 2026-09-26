import { useEffect, useRef, useState } from 'react';

// Голосовой ввод через Web Speech API браузера, русский язык. Есть в Chrome и Edge; в Firefox API нет,
// тогда кнопка микрофона не показывается и остаётся ввод текстом.

interface RecognitionResult {
  isFinal: boolean;
  0: { transcript: string };
}

interface Recognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: { results: ArrayLike<RecognitionResult> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
}

type RecognitionCtor = new () => Recognition;

function recognitionClass(): RecognitionCtor | null {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** onText получает распознанный текст по ходу речи и ещё раз с final = true, когда фраза закончена. */
export function useSpeech(onText: (text: string, final: boolean) => void) {
  const [listening, setListening] = useState(false);
  const recognition = useRef<Recognition | null>(null);
  const handler = useRef(onText);
  const Ctor = recognitionClass();

  useEffect(() => {
    handler.current = onText;
  }, [onText]);

  useEffect(() => () => recognition.current?.stop(), []);

  const start = () => {
    if (!Ctor) return;
    const r = new Ctor();
    r.lang = 'ru-RU';
    r.interimResults = true;
    r.continuous = false;
    r.onresult = (e) => {
      const parts = Array.from(e.results);
      const text = parts.map((p) => p[0].transcript).join(' ').trim();
      handler.current(text, parts.at(-1)?.isFinal ?? false);
    };
    r.onend = () => setListening(false);
    r.onerror = () => setListening(false);
    recognition.current = r;
    setListening(true);
    r.start();
  };

  const stop = () => recognition.current?.stop();

  return { supported: Ctor != null, listening, start, stop };
}
