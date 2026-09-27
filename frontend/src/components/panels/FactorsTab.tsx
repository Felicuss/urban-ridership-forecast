import { useCalendar, useFactors } from '../../api/queries';
import { useWeatherGrid } from '../../hooks/useWeather';
import { CENTER_INDEX, beyondForecast } from '../../lib/weatherGrid';
import { useStore } from '../../state/store';
import { HORIZON_START, MONTHS, dayIndex, dayLabel, hourOf, isoDate, monthLabel, monthOf, shortDate } from '../../lib/time';
import { capitalize, fmt1, fmtCompact, fmtTemp } from '../../lib/format';
import { routeColor } from '../../lib/routes';
import { MiniBars, MiniLine } from '../charts/Mini';
import { Card, TramDots } from '../ui/Controls';
import styles from './Panels.module.css';

const HOURS = Array.from({ length: 24 }, (_, h) => `${h}`);
const DAY_COLORS: Record<string, string> = { workday: '#26282e', saturday: '#3b3e46', sunday: '#51555f', holiday: '#e5737d' };

export default function FactorsTab() {
  const factors = useFactors().data;
  const calendar = useCalendar().data;
  const day = useStore((s) => dayIndex(s.minute));
  const hour = useStore((s) => hourOf(s.minute));
  const route = useStore((s) => s.route);
  const setDay = useStore((s) => s.setDay);
  const grid = useWeatherGrid(isoDate(day));
  if (!factors) return <TramDots label="Загружаем внешние данные" />;
  const w = factors.weather;
  const center = grid.data?.[CENTER_INDEX];
  const dailyTemp = w.temp.map((row) => avg(row));
  const dailyPrecip = w.precip.map((row) => row.reduce<number>((a, v) => a + (v ?? 0), 0));
  const horizonDay = w.dates.indexOf(isoDate(day));
  const traffic = factors.traffic;
  const city = factors.city_ridership;
  const cityFrom = city.months.indexOf('2023-01');
  const sched = factors.schedule.routes[String(route ?? 17)];
  const month = monthOf(day);
  const monthDays = calendar?.slice(month.first, month.first + month.days) ?? [];
  const holidays = monthDays.filter((c) => c.holiday);
  const monthKey = isoDate(month.first).slice(0, 7);
  const trafficIndex = traffic.months.indexOf(monthKey);

  return (
    <div className={styles.stack}>
      <Card title={`Погода: ${dayLabel(day)}`}
        info="Open-Meteo по часам для центра Москвы: архив для прошлых дат, прогноз для ближайших 16 дней. На проверке организаторов поправка на погоду снизила точность на 0,26 п. п., поэтому в прогнозе по умолчанию она выключена; включить можно на вкладке «Сценарий».">
        {center ? (
          <>
            <MiniLine values={center.temp} labels={HOURS} color="#e0af68" mark={hour} format={(v) => fmtTemp(v)} />
            <MiniBars values={center.rain.map((v, i) => (v ?? 0) + (center.snow[i] ?? 0))} color="#7aa2f7"
              mark={hour} height={46} />
            <p className={styles.note}>Температура по часам и осадки (дождь, мм/ч, и снег, см/ч). Эффект на посадки по
              истории 2025 года: −0,74 % на мм осадков за день.{' '}
              <a href="https://open-meteo.com/en/docs/historical-weather-api" target="_blank" rel="noopener noreferrer">Open-Meteo</a></p>
          </>
        ) : (
          <p className={styles.note}>{grid.isLoading ? 'Загружаем погоду…'
            : beyondForecast(isoDate(day)) ? 'Для этой даты погоды нет: прогноз Open-Meteo выпускается на 16 дней вперёд.'
              : 'Open-Meteo не ответил, погода за этот день не загрузилась.'}</p>
        )}
      </Card>

      <Card title="Погода за горизонт прогноза" info="Средняя температура суток и сумма осадков за 1 ноября – 31 декабря 2025, центр Москвы.">
        <MiniLine values={dailyTemp} labels={w.dates.map(shortDate)} color="#e0af68"
          mark={horizonDay >= 0 ? horizonDay : undefined} format={(v) => fmtTemp(v)} />
        <MiniBars values={dailyPrecip} color="#7aa2f7" mark={horizonDay >= 0 ? horizonDay : undefined} height={40} />
      </Card>

      <Card title={`Календарь: ${MONTHS[month.month]} ${month.year}`}
        info="Производственный календарь: 2025 год по постановлению № 1335, 2026 год по isdayoff.ru, 2027 год по постановлению №1187. Оценка 2026–2027 учитывает тип дня; следующие поправки относятся только к прогнозу ноября–декабря 2025. Праздник в будний день прогнозируется как воскресенье ×0,95, рабочая суббота 1 ноября ×0,85 к будню, 29–30 декабря ×0,85, 31 декабря днём ×0,9 и ноль после 20:00: бесплатный проезд.">
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.max(monthDays.length, 1)}, 1fr)`, gap: 2 }}>
          {monthDays.map((c, i) => (
            <button key={c.date} type="button" title={`${c.date}${c.holiday ? `, ${c.holiday}` : ''}`}
              onClick={() => setDay(month.first + i)}
              style={{ height: 22, borderRadius: 3, background: c.holiday ? DAY_COLORS.holiday
                : !c.dayOff && c.dayOfWeek >= 5 ? '#e0af68' : DAY_COLORS[c.dayType] ?? '#26282e',
              outline: month.first + i === day ? '1.5px solid #f4f4f5' : 'none' }} />
          ))}
        </div>
        <ul className={styles.list}>
          {holidays.map((c) => <li key={c.date}><span>{shortDate(c.date)} — {c.holiday}</span></li>)}
          {holidays.length === 0 && <li><span className={styles.note}>Праздников в этом месяце нет.</span></li>}
        </ul>
        <p className={styles.note}>
          <a href="https://www.consultant.ru/law/ref/calendar/proizvodstvennye/2025/" target="_blank" rel="noopener noreferrer">Постановление № 1335</a>,{' '}
          <a href="https://isdayoff.ru/" target="_blank" rel="noopener noreferrer">isdayoff.ru</a></p>
      </Card>

      <Card title="Загруженность дорог"
        info="data.mos.ru, набор 62525: средний балл пробок по месяцам. Рост на 1 балл сопровождается ростом посадок трамвая Москвы на 10,5 % (p = 0,0001). Вес трафика в уровне ноября–декабря настраивается на вкладке «Сценарий».">
        <MiniBars values={traffic.score} labels={traffic.months}
          color="#bb9af7" highlight={(i) => i === trafficIndex} />
        <p className={styles.note}>
          {trafficIndex >= 0
            ? `${capitalize(monthLabel(monthKey))}: ${fmt1(traffic.score[trafficIndex])} балла, выделен столбиком. `
            : `За ${monthLabel(monthKey)} балла ещё нет: последний месяц в наборе - ${monthLabel(traffic.months[traffic.months.length - 1] ?? monthKey)}. `}
          Почему по месяцам, а не по часам: полного почасового ряда пробок Москвы в открытых данных нет. data.mos.ru
          публикует средний балл за месяц, а баллы ЦОДД в постах Дептранса выходят несколько раз в день, 386 постов
          за 2025 год, в основном вечером в будни. Поэтому пробки двигают уровень месяца в прогнозе, а не отдельный
          час.{' '}
          <a href="https://data.mos.ru/opendata/62525" target="_blank" rel="noopener noreferrer">data.mos.ru, набор 62525</a></p>
      </Card>

      <Card title="Трамвай Москвы по месяцам"
        info="data.mos.ru, набор 62521: посадки в сутки по всем трамвайным маршрутам города. Из отношения месяцев прошлых лет к октябрю строится уровень ноября и декабря (амплитуда наших маршрутов 0,83) и годовой прогноз.">
        <MiniLine values={city.per_day.slice(cityFrom)} labels={city.months.slice(cityFrom)}
          color="#73daca" mark={city.months.indexOf('2025-11') - cityFrom} format={(v) => fmtCompact(v)} />
        <p className={styles.note}>Отметка — ноябрь 2025. {capitalize(monthLabel(city.months[city.months.length - 1] ?? '2026-08'))}: {fmtCompact(city.per_day[city.per_day.length - 1])} посадок в сутки.{' '}
          <a href="https://data.mos.ru/opendata/7704786030-mesyachniy-passajiropotok-po-vsem-vidam-obshchestvennogo-transporta-v-gorode-moskve"
            target="_blank" rel="noopener noreferrer">data.mos.ru, набор 62521</a></p>
      </Card>

      {sched && (
        <Card title={`Интервал движения: маршрут ${route ?? 17}`}
          info={`${factors.schedule.source}, выгрузка ${factors.schedule.fetched_at}. Это действующее расписание, а не расписание ноября 2025: используем его как оценку числа рейсов в час.`}>
          <MiniBars values={(sched.weekday?.headway_min ?? []).map((v) => v ?? 0)} labels={HOURS} color={routeColor(route ?? 17)} mark={hour} />
          <p className={styles.note}>Будни: работает {sched.weekday?.service_from}–{sched.weekday?.service_to}, выходные:
            {' '}{sched.weekend?.service_from}–{sched.weekend?.service_to}. Столбик — интервал в минутах, выше — реже.{' '}
            <a href={sched.page} target="_blank" rel="noopener noreferrer">Страница маршрута</a></p>
        </Card>
      )}

      <Card title="События сети" info="Разбор постов Telegram-канала «Дептранс. Оперативно», mos.ru и sobyanin.ru. На проверке организаторов возврат выходных рейсов 7 и 50 с 15.11 поднял точность на 1,16 п. п., запуск маршрута 5 с 16.12 — на 0,41 п. п.">
        <ul className={styles.list}>
          {factors.events.map((e) => (
            <li key={`${e.start}-${e.description}`}>
              <span><b>{shortDate(e.start)}{e.end && e.end !== e.start ? `–${shortDate(e.end)}` : ''}</b> {e.description}</span>
              <small>{e.routes === 'all' ? 'все маршруты' : `${e.routes.includes(';') ? 'маршруты' : 'маршрут'} ${e.routes.replaceAll(';', ', ')}`}
                {e.effect ? `; ${e.start < HORIZON_START ? 'в данных' : 'эффект'}: ${e.effect}` : ''}{' '}
                {e.source.startsWith('http') && <a href={e.source} target="_blank" rel="noopener noreferrer">источник</a>}</small>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function avg(row: (number | null)[]): number | null {
  const v = row.filter((x): x is number => x != null);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}
