import { useEffect, useState, type ReactNode } from 'react';
import { useCalendar, useFactors } from '../../api/queries';
import { SPEEDS, isDefaultScenario, useStore, type Speed } from '../../state/store';
import { useLayout, type LayoutMode } from '../../state/layout';
import { TIMELINE_DAYS, clock, dayIndex, dayLabel, hourOf, isoDate, sunElevation, weekdayName } from '../../lib/time';
import { fmtTemp, fmt1 } from '../../lib/format';
import { SKY_LABEL, weatherAt } from '../../lib/weather';
import { useTarget } from '../../hooks/useTarget';
import { centerWeather, useWeatherGrid } from '../../hooks/useWeather';
import { Icon, SkyIcon } from '../ui/Icons';
import { SettingsSheet } from './SettingsSheet';
import { ExportSheet } from './ExportSheet';
import { AgentIsland } from '../agent/AgentIsland';
import { DatePopover } from './DatePopover';
import { useAlerts } from '../../hooks/useDispatch';
import styles from './TopBar.module.css';

const SOURCE_BADGE: Record<string, { label: string; hint: string }> = {
  fact: { label: 'факт', hint: 'Успешные валидации из данных организаторов' },
  forecast: { label: 'прогноз', hint: 'Почасовой прогноз v11, точность 0,90741 на проверке организаторов' },
  outlook: { label: 'оценка', hint: 'Месячный прогноз по сезонному индексу, разложенный по дням и часам; коридор ±12 %' },
};

const SPEED_HINT: Record<Speed, string> = {
  1: 'настоящее время',
  60: 'минута за секунду',
  300: '5 минут за секунду',
  900: '15 минут за секунду',
  3600: 'сутки за 24 секунды',
};

export function TopBar() {
  const minute = useStore((s) => Math.floor(s.minute));
  const followNow = useStore((s) => s.followNow);
  const setFollowNow = useStore((s) => s.setFollowNow);
  const setDay = useStore((s) => s.setDay);
  const playing = useStore((s) => s.playing);
  const speed = useStore((s) => s.speed);
  const togglePlay = useStore((s) => s.togglePlay);
  const setSpeed = useStore((s) => s.setSpeed);
  const setSettingsOpen = useStore((s) => s.setSettingsOpen);
  const settingsOpen = useStore((s) => s.settingsOpen);
  const scenario = useStore((s) => s.scenario);
  const resetScenario = useStore((s) => s.resetScenario);
  const factors = useFactors().data;
  const calendar = useCalendar().data;
  const target = useTarget();
  const [dateOpen, setDateOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const day = dayIndex(minute);
  const hour = hourOf(minute);
  const cal = calendar?.[day];
  const grid = useWeatherGrid(isoDate(day)).data;
  const fallbackDay = factors ? factors.weather.dates.indexOf(isoDate(day)) : -1;
  const w = centerWeather(grid, hour) ?? (fallbackDay >= 0 ? weatherAt(factors?.weather, fallbackDay, hour) : null);
  const changes = Object.keys(scenario.coefficients).length + scenario.events.length;
  const night = sunElevation(minute) < -4;
  const badge = SOURCE_BADGE[cal?.source ?? 'forecast'];
  const setBoardOpen = useStore((s) => s.setBoardOpen);
  const openBoard = () => {
    setBoardOpen(true);
    void document.documentElement.requestFullscreen?.().catch(() => undefined);
  };


  return (
    <header className={styles.bar}>
      <div className={styles.brand}>
        <span className={styles.logo} aria-hidden="true">
          <svg viewBox="0 0 32 32" width="28" height="28">
            <rect width="32" height="32" rx="9" fill="#18181b" />
            <path d="M8 22h16v2.5a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2z" fill="#7aa2f7" />
            <path d="M9 12.5a4 4 0 0 1 4-4h6a4 4 0 0 1 4 4V22H9z" fill="#f4f4f5" />
            <rect x="11.2" y="11" width="9.6" height="5.4" rx="1.6" fill="#18181b" />
            <path d="M16 4.5v4M13 4.5h6" stroke="#e5737d" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </span>
        <div>
          <div className={styles.title}>Час пик</div>
          <div className={styles.subtitle}>посадки в трамваи Москвы по часам</div>
        </div>
      </div>

      <div className={styles.when}>
        <button type="button" className={styles.icon} aria-label="Предыдущий день" disabled={day === 0}
          title={followNow ? 'Предыдущий день: режим «Сейчас» выключится' : 'Предыдущий день'} onClick={() => setDay(day - 1)}><Icon.prev /></button>
        <button type="button" className={styles.date} onClick={() => setDateOpen((v) => !v)} aria-expanded={dateOpen}
          title={followNow ? 'Выбрать дату в календаре: режим «Сейчас» выключится' : 'Выбрать дату в календаре'}>
          <Icon.calendar />
          <DateText day={day} />
          {cal?.dayOff && <em className={cal.holiday ? styles.holiday : styles.dayoff}>{cal.holiday ? 'праздник' : 'выходной'}</em>}
          {cal && !cal.dayOff && cal.dayOfWeek >= 5 && <em className={styles.work}>рабочий выходной</em>}
        </button>
        <button type="button" className={styles.icon} aria-label="Следующий день" disabled={day === TIMELINE_DAYS - 1}
          title={followNow ? 'Следующий день: режим «Сейчас» выключится' : 'Следующий день'} onClick={() => setDay(day + 1)}><Icon.next /></button>
        {badge && <span className={`${styles.source} ${styles[cal?.source ?? 'forecast']}`} title={badge.hint}>{badge.label}</span>}
        {dateOpen && <DatePopover day={day} calendar={calendar} onPick={(d) => { setDay(d); setDateOpen(false); }}
          onClose={() => setDateOpen(false)} />}
      </div>

      <div className={styles.clock}>
        <span className="num">{clock(minute)}</span>
        <button type="button" className={styles.play} onClick={togglePlay} aria-label={playing ? 'Пауза' : 'Пустить время'}
          title={playing ? 'Пауза' : followNow ? 'Пустить время: режим «Сейчас» выключится'
            : `Пустить время, ${SPEED_HINT[speed]}`}>
          {playing ? <Icon.pause /> : <Icon.play />}
        </button>
        <select className={styles.speedSelect} value={speed} aria-label="Скорость времени"
          title={`Скорость времени: ${SPEED_HINT[speed]}`} onChange={(e) => setSpeed(Number(e.target.value) as Speed)}>
          {SPEEDS.map((s) => <option key={s} value={s} title={SPEED_HINT[s]}>×{s}</option>)}
        </select>
        <button type="button" className={followNow ? styles.nowOn : styles.now} onClick={() => setFollowNow(!followNow)}
          aria-pressed={followNow} title={followNow
            ? 'Идёт настоящее время по Москве. Другая дата, час или запуск времени выключат этот режим'
            : 'Текущие дата и время по Москве'}>
          <i />Сейчас
        </button>
      </div>

      {w && (
        <div className={styles.weather} title={grid ? `Open-Meteo, центр Москвы, ${hour}:00` : 'Open-Meteo, архив'}>
          <SkyIcon sky={w.sky} night={night} />
          <span className="num">{fmtTemp(w.temp)}</span>
          <span className={styles.wlabel}>{SKY_LABEL[w.sky]}{w.precip > 0.05 ? `, ${fmt1(w.precip)} мм` : ''}</span>
        </div>
      )}

      <div className={styles.actions}>
        <AgentIsland />
        {changes > 0 && !isDefaultScenario(scenario) && (
          <button type="button" className={styles.scenario} onClick={resetScenario}
            title={`Сценарий: ${changes} ${changes === 1 ? 'изменение' : changes < 5 ? 'изменения' : 'изменений'}. Клик вернёт прогноз по умолчанию`}>
            Сценарий: {changes}
            <Icon.reset />
          </button>
        )}
        <AlertBell />
        <LayoutSwitch />
        <button type="button" className={styles.icon} aria-label="Табло" onClick={openBoard}
          title="Табло на большой экран диспетчерской: крупные числа, маршруты сменяются сами">
          <Icon.board />
        </button>
        <div className={styles.export}>
          <button type="button" onClick={() => setExportOpen(true)} aria-label="Выгрузка"
            title={`Выгрузка в CSV или XLSX: ${target.name} или вся сеть, любой период и шаг`}>
            <Icon.download /><span className={styles.exportLabel}>Выгрузка</span>
          </button>
        </div>
        <button type="button" className={styles.icon} aria-label="Настройки" onClick={() => setSettingsOpen(true)}
          title="Настройки: слои карты, погода, свет по времени суток, анимации">
          <Icon.gear />
        </button>
      </div>
      {settingsOpen && <SettingsSheet onClose={() => setSettingsOpen(false)} />}
      {exportOpen && <ExportSheet onClose={() => setExportOpen(false)} />}
      <NowNotice />
    </header>
  );
}

const LAYOUTS: { mode: LayoutMode; label: string; hint: string; icon: ReactNode }[] = [
  { mode: 'map', label: 'Карта', hint: 'Карта во весь экран (V - следующая раскладка)',
    icon: <svg viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="4" width="14" height="12" rx="2" /></svg> },
  { mode: 'split', label: 'Сплит', hint: 'Сплит: карта и выбранный виджет рядом',
    icon: <svg viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="4" width="7" height="12" rx="1.5" /><rect x="11.5" y="4" width="5.5" height="12" rx="1.5" /></svg> },
  { mode: 'panels', label: 'Панели', hint: 'Панели: 2-4 виджета на экране без карты, место меняется перетаскиванием',
    icon: <svg viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="4" width="6.5" height="5.5" rx="1.2" /><rect x="10.5" y="4" width="6.5" height="5.5" rx="1.2" /><rect x="3" y="10.5" width="6.5" height="5.5" rx="1.2" /><rect x="10.5" y="10.5" width="6.5" height="5.5" rx="1.2" /></svg> },
];

/** Раскладка главной области: карта, сплит или панели виджетов. */
function LayoutSwitch() {
  const mode = useLayout((s) => s.mode);
  const setMode = useLayout((s) => s.setMode);
  return (
    <div className={styles.layout} role="radiogroup" aria-label="Раскладка экрана">
      {LAYOUTS.map((l) => (
        <button key={l.mode} type="button" role="radio" aria-checked={mode === l.mode} aria-label={l.label} title={l.hint}
          className={mode === l.mode ? styles.layoutOn : styles.layoutBtn} onClick={() => setMode(l.mode)}>{l.icon}</button>
      ))}
    </div>
  );
}

/** Плашка после ручного выбора времени: режим «Сейчас» выключен, его можно вернуть одной кнопкой. */
function NowNotice() {
  const at = useStore((s) => s.nowNotice);
  const dismiss = useStore((s) => s.dismissNowNotice);
  const setFollowNow = useStore((s) => s.setFollowNow);
  useEffect(() => {
    if (at == null) return undefined;
    const t = setTimeout(dismiss, NOTICE_MS);
    return () => clearTimeout(t);
  }, [at, dismiss]);
  if (at == null) return null;
  return (
    <div key={at} className={styles.notice} role="status">
      <span>Режим «Сейчас» выключен: выбрано другое время.</span>
      <button type="button" className={styles.noticeBack} onClick={() => setFollowNow(true)}>Вернуть «Сейчас»</button>
      <button type="button" className={styles.noticeClose} aria-label="Закрыть" onClick={dismiss}><Icon.close /></button>
    </div>
  );
}

const NOTICE_MS = 6000;

/** Колокольчик: сколько подписок сработало на завтра. Клик открывает оповещения во вкладке «Смена». */
function AlertBell() {
  const { states, day } = useAlerts();
  const setTab = useStore((s) => s.setTab);
  const fired = states.filter((s) => s.spans.length > 0).length;
  const hint = states.length === 0
    ? 'Оповещения: подпишитесь на маршрут во вкладке «Смена»'
    : fired ? `Завтра, ${dayLabel(day, false)}: сработало ${fired} из ${states.length} оповещений`
      : `Завтра, ${dayLabel(day, false)}: все ${states.length} оповещений в норме`;
  return (
    <button type="button" className={fired ? styles.bellOn : styles.icon} aria-label={hint} title={hint}
      onClick={() => {
        setTab('shift');
        setTimeout(() => document.getElementById('shift-alerts')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 350);
      }}>
      <Icon.bell />
      {fired > 0 && <i className={styles.bellCount}>{fired}</i>}
    </button>
  );
}

/** Дата в кнопке: год прячется на узком экране, день недели остаётся всегда. */
/** «сб, 25 октября»: короткий день недели, чтобы ширина кнопки почти не менялась при листании стрелками. */
function DateText({ day }: { day: number }) {
  const label = dayLabel(day);
  const date = label.slice(0, label.indexOf(','));
  return <span>{weekdayName(day, true)}, {date.slice(0, -5)}<span className={styles.year}>{date.slice(-5)}</span></span>;
}
