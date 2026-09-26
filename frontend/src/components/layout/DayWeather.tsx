import { useWeatherGrid } from '../../hooks/useWeather';
import { CENTER_INDEX, SNOW_CM_TO_MM } from '../../lib/weatherGrid';
import { MINUTES_PER_DAY, isoDate, sunElevation } from '../../lib/time';
import { skyOf } from '../../lib/weather';
import { fmt1, fmtTemp } from '../../lib/format';
import { SkyIcon } from '../ui/Icons';
import styles from './DayWeather.module.css';

// Погода на весь выбранный день под графиком суток: небо и температура каждые 3 часа на тех же
// позициях, что и метки часов, и осадки по часам столбиками. Центр Москвы, Open-Meteo.

const BLOCKS = [0, 3, 6, 9, 12, 15, 18, 21];
/** Столбик осадков в полную высоту от 3 мм в час. */
const FULL_MM = 3;

export function DayWeather({ day, hour }: { day: number; hour: number }) {
  const grid = useWeatherGrid(isoDate(day));
  const c = grid.data?.[CENTER_INDEX];
  if (!c) {
    return (
      <div className={styles.empty}>
        {grid.isLoading ? 'Загружаем погоду на день…' : 'Погоды на эту дату нет: прогноз выходит на 16 дней вперёд'}
      </div>
    );
  }
  const temps = c.temp.filter((v): v is number => v != null);
  const precip = c.rain.map((r, i) => (r ?? 0) + (c.snow[i] ?? 0) * SNOW_CM_TO_MM);
  const total = precip.reduce((a, b) => a + b, 0);
  const summary = `Погода за день, центр Москвы: ${fmtTemp(Math.min(...temps))}…${fmtTemp(Math.max(...temps))}`
    + (total > 0.05 ? `, осадки ${fmt1(total)} мм` : ', без осадков');
  return (
    <div className={styles.row} title={summary} aria-label={summary}>
      <div className={styles.blocks}>
        {BLOCKS.map((h) => {
          const mid = h + 1;
          const night = sunElevation(day * MINUTES_PER_DAY + mid * 60 + 30) < -4;
          return (
            <span key={h} className={hour >= h && hour < h + 3 ? styles.blockOn : styles.block}
              style={{ left: `${((h + 1.5) / 24) * 100}%` }}>
              <SkyIcon sky={skyOf(c.code[mid])} night={night} />
              <b className="num">{fmtTemp(c.temp[mid])}</b>
            </span>
          );
        })}
      </div>
      <div className={styles.bars} aria-hidden="true">
        {precip.map((mm, h) => (
          <i key={h} className={(c.snow[h] ?? 0) * SNOW_CM_TO_MM > (c.rain[h] ?? 0) ? styles.snow : styles.rain}
            style={{ height: `${Math.min(mm / FULL_MM, 1) * 100}%`, opacity: h === hour ? 1 : 0.75 }} />
        ))}
      </div>
    </div>
  );
}
