import { useState } from 'react';
import { download, useCalendar, useFactors } from '../../api/queries';
import { SPEEDS, isDefaultScenario, useStore, type Speed } from '../../state/store';
import { TIMELINE_DAYS, clock, dayIndex, dayLabel, hourOf, isoDate, sunElevation } from '../../lib/time';
import { fmtTemp, fmt1 } from '../../lib/format';
import { SKY_LABEL, weatherAt } from '../../lib/weather';
import { targetQuery, useTarget } from '../../hooks/useTarget';
import { centerWeather, useWeatherGrid } from '../../hooks/useWeather';
import { Icon, SkyIcon } from '../ui/Icons';
import { SettingsSheet } from './SettingsSheet';
import { DatePopover } from './DatePopover';
import styles from './TopBar.module.css';

const SOURCE_BADGE: Record<string, { label: string; hint: string }> = {
  fact: { label: 'факт', hint: 'Успешные валидации из данных организаторов' },
  forecast: { label: 'прогноз', hint: 'Почасовой прогноз модели, точность 0,8995 на проверке организаторов' },
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
  const horizon = useStore((s) => s.horizon);
  const factors = useFactors().data;
  const calendar = useCalendar().data;
  const target = useTarget();
  const [dateOpen, setDateOpen] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const day = dayIndex(minute);
  const hour = hourOf(minute);
  const cal = calendar?.[day];
  const grid = useWeatherGrid(isoDate(day)).data;
  const fallbackDay = factors ? factors.weather.dates.indexOf(isoDate(day)) : -1;
  const w = centerWeather(grid, hour) ?? (fallbackDay >= 0 ? weatherAt(factors?.weather, fallbackDay, hour) : null);
  const changes = Object.keys(scenario.coefficients).length + scenario.events.length;
  const night = sunElevation(minute) < -4;
  const badge = SOURCE_BADGE[cal?.source ?? 'forecast'];

  const exportFile = async (format: 'csv' | 'xlsx') => {
    setExporting(format);
    setExportError(null);
    try {
      const { id, ...rest } = targetQuery(target);
      const period = horizon === 'day' ? { from: isoDate(day), to: isoDate(day), granularity: 'hour' as const }
        : horizon === 'month' ? { horizon: 'month' as const, from: isoDate(day) } : { horizon: 'year' as const };
      await download(format, { ...rest, ids: id ? [id] : undefined, ...period }, scenario);
    } catch (e) {
      setExportError(`Выгрузка не удалась: ${e instanceof Error ? e.message : 'сервис недоступен'}`);
    } finally {
      setExporting(null);
    }
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
          <div className={styles.title}>Трамвай</div>
          <div className={styles.subtitle}>прогноз посадок по часам</div>
        </div>
      </div>

      <div className={styles.when}>
        <button type="button" className={styles.icon} aria-label="Предыдущий день" disabled={day === 0}
          onClick={() => setDay(day - 1)}><Icon.prev /></button>
        <button type="button" className={styles.date} onClick={() => setDateOpen((v) => !v)} aria-expanded={dateOpen}>
          <Icon.calendar />
          <span>{dayLabel(day)}</span>
          {cal?.dayOff && <em className={cal.holiday ? styles.holiday : styles.dayoff}>{cal.holiday ? 'праздник' : 'выходной'}</em>}
          {cal && !cal.dayOff && cal.dayOfWeek >= 5 && <em className={styles.work}>рабочий выходной</em>}
        </button>
        <button type="button" className={styles.icon} aria-label="Следующий день" disabled={day === TIMELINE_DAYS - 1}
          onClick={() => setDay(day + 1)}><Icon.next /></button>
        {badge && <span className={`${styles.source} ${styles[cal?.source ?? 'forecast']}`} title={badge.hint}>{badge.label}</span>}
        {dateOpen && <DatePopover day={day} calendar={calendar} onPick={(d) => { setDay(d); setDateOpen(false); }}
          onClose={() => setDateOpen(false)} />}
      </div>

      <div className={styles.clock}>
        <span className="num">{clock(minute)}</span>
        <button type="button" className={styles.play} onClick={togglePlay} aria-label={playing ? 'Пауза' : 'Пустить время'}
          title={playing ? 'Пауза' : `Пустить время, ${SPEED_HINT[speed]}`}>
          {playing ? <Icon.pause /> : <Icon.play />}
        </button>
        <div className={styles.speeds} role="radiogroup" aria-label="Скорость времени">
          {SPEEDS.map((s) => (
            <button key={s} type="button" role="radio" aria-checked={s === speed} title={SPEED_HINT[s]}
              className={s === speed ? styles.speedOn : styles.speed} onClick={() => setSpeed(s)}>×{s}</button>
          ))}
        </div>
        <button type="button" className={followNow ? styles.nowOn : styles.now} onClick={() => setFollowNow(!followNow)}
          title="Текущие дата и время по Москве">
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
        {changes > 0 && !isDefaultScenario(scenario) && (
          <button type="button" className={styles.scenario} onClick={resetScenario} title="Вернуть прогноз по умолчанию">
            Сценарий: {changes} {changes === 1 ? 'изменение' : changes < 5 ? 'изменения' : 'изменений'}
            <Icon.reset />
          </button>
        )}
        <div className={styles.export}>
          <button type="button" onClick={() => void exportFile('csv')} disabled={exporting != null}
            title={`Выгрузить: ${target.name}, горизонт как в панели прогноза`}>
            <Icon.download />{exporting === 'csv' ? 'CSV…' : 'CSV'}
          </button>
          <button type="button" onClick={() => void exportFile('xlsx')} disabled={exporting != null}>
            {exporting === 'xlsx' ? 'XLSX…' : 'XLSX'}
          </button>
        </div>
        {exportError && <span className={styles.exportError} role="alert" title={exportError}>{exportError}</span>}
        <button type="button" className={styles.icon} aria-label="Настройки" onClick={() => setSettingsOpen(true)}>
          <Icon.gear />
        </button>
      </div>
      {settingsOpen && <SettingsSheet onClose={() => setSettingsOpen(false)} />}
    </header>
  );
}
