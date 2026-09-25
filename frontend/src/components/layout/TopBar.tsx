import { useState } from 'react';
import { download, useFactors } from '../../api/queries';
import { isDefaultScenario, useStore } from '../../state/store';
import { HORIZON_DAYS, HORIZON_START, clock, dayIndex, dayLabel, hourOf, isoDate, sunElevation } from '../../lib/time';
import { fmtTemp, fmt1 } from '../../lib/format';
import { SKY_LABEL, weatherAt } from '../../lib/weather';
import { useTarget } from '../../hooks/useTarget';
import { Icon, SkyIcon } from '../ui/Icons';
import { SettingsSheet } from './SettingsSheet';
import { DatePopover } from './DatePopover';
import styles from './TopBar.module.css';

export function TopBar() {
  const minute = useStore((s) => Math.floor(s.minute));
  const followNow = useStore((s) => s.followNow);
  const setFollowNow = useStore((s) => s.setFollowNow);
  const setDay = useStore((s) => s.setDay);
  const setSettingsOpen = useStore((s) => s.setSettingsOpen);
  const settingsOpen = useStore((s) => s.settingsOpen);
  const scenario = useStore((s) => s.scenario);
  const resetScenario = useStore((s) => s.resetScenario);
  const horizon = useStore((s) => s.horizon);
  const factors = useFactors().data;
  const target = useTarget();
  const [dateOpen, setDateOpen] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);
  const day = dayIndex(minute);
  const hour = hourOf(minute);
  const cal = factors?.calendar[day];
  const w = weatherAt(factors?.weather, day, hour);
  const changes = Object.keys(scenario.coefficients).length + scenario.events.length;
  const night = sunElevation(minute) < -4;

  const exportFile = async (format: 'csv' | 'xlsx') => {
    setExporting(format);
    try {
      const level = target.level === 'segment' ? 'route' : target.level;
      const period = horizon === 'day' ? { from: isoDate(day), to: isoDate(day), granularity: 'hour' as const }
        : horizon === 'month' ? { horizon: 'month' as const, from: isoDate(day) } : { horizon: 'year' as const };
      await download(format, { level, ids: target.id ? [target.id] : undefined, ...period }, scenario);
    } finally {
      setExporting(null);
    }
  };

  return (
    <header className={styles.bar}>
      <div className={styles.brand}>
        <span className={styles.logo} aria-hidden="true">
          <svg viewBox="0 0 32 32" width="28" height="28">
            <rect width="32" height="32" rx="9" fill="#0f1a2b" />
            <path d="M8 22h16v2.5a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2z" fill="#2d82e6" />
            <path d="M9 12.5a4 4 0 0 1 4-4h6a4 4 0 0 1 4 4V22H9z" fill="#f4f7fb" />
            <rect x="11.2" y="11" width="9.6" height="5.4" rx="1.6" fill="#0f1a2b" />
            <path d="M16 4.5v4M13 4.5h6" stroke="#ef4136" strokeWidth="1.8" strokeLinecap="round" />
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
          {cal && cal.day_off && <em className={cal.holiday ? styles.holiday : styles.dayoff}>
            {cal.holiday ? 'праздник' : 'выходной'}</em>}
          {cal && !cal.day_off && cal.dow === 5 && <em className={styles.work}>рабочая суббота</em>}
        </button>
        <button type="button" className={styles.icon} aria-label="Следующий день" disabled={day === HORIZON_DAYS - 1}
          onClick={() => setDay(day + 1)}><Icon.next /></button>
        {dateOpen && <DatePopover day={day} onPick={(d) => { setDay(d); setDateOpen(false); }}
          onClose={() => setDateOpen(false)} calendar={factors?.calendar} />}
      </div>

      <div className={styles.clock}>
        <span className="num">{clock(minute)}</span>
        <button type="button" className={followNow ? styles.nowOn : styles.now} onClick={() => setFollowNow(!followNow)}
          title={`Текущее время суток и такой же день недели во второй неделе горизонта (с ${HORIZON_START})`}>
          <i />Сейчас
        </button>
      </div>

      {w && (
        <div className={styles.weather} title={`Open-Meteo, центр Москвы, ${hour}:00`}>
          <SkyIcon sky={w.sky} night={night} />
          <span className="num">{fmtTemp(w.temp)}</span>
          <span className={styles.wlabel}>
            {SKY_LABEL[w.sky]}{w.precip > 0 ? `, ${fmt1(w.precip)} мм` : ''}
          </span>
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
            title={`Выгрузить прогноз: ${target.name}, горизонт как в панели прогноза`}>
            <Icon.download />{exporting === 'csv' ? 'CSV…' : 'CSV'}
          </button>
          <button type="button" onClick={() => void exportFile('xlsx')} disabled={exporting != null}>
            {exporting === 'xlsx' ? 'XLSX…' : 'XLSX'}
          </button>
        </div>
        <button type="button" className={styles.icon} aria-label="Настройки" onClick={() => setSettingsOpen(true)}>
          <Icon.gear />
        </button>
      </div>
      {settingsOpen && <SettingsSheet onClose={() => setSettingsOpen(false)} />}
    </header>
  );
}
