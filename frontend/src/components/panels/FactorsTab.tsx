import { useFactors } from '../../api/queries';
import { useStore } from '../../state/store';
import { dayIndex, dayLabel, hourOf, monthLabel, shortDate } from '../../lib/time';
import { fmt1, fmtCompact, fmtTemp } from '../../lib/format';
import { routeColor } from '../../lib/routes';
import { MiniBars, MiniLine } from '../charts/Mini';
import { Card, TramDots } from '../ui/Controls';
import styles from './Panels.module.css';

const HOURS = Array.from({ length: 24 }, (_, h) => `${h}`);
const DAY_COLORS: Record<string, string> = { workday: '#1f2c3d', saturday: '#3a4a60', sunday: '#56687f', holiday: '#ef4136' };

export default function FactorsTab() {
  const factors = useFactors().data;
  const day = useStore((s) => dayIndex(s.minute));
  const hour = useStore((s) => hourOf(s.minute));
  const route = useStore((s) => s.route);
  const setDay = useStore((s) => s.setDay);
  if (!factors) return <TramDots label="Загружаем внешние данные" />;
  const w = factors.weather;
  const dailyTemp = w.temp.map((row) => avg(row));
  const dailyPrecip = w.precip.map((row) => row.reduce<number>((a, v) => a + (v ?? 0), 0));
  const traffic = factors.traffic;
  const city = factors.city_ridership;
  const cityFrom = city.months.indexOf('2023-01');
  const sched = factors.schedule.routes[String(route ?? 17)];
  const holidays = factors.calendar.filter((c) => c.holiday);

  return (
    <div className={styles.stack}>
      <Card title={`Погода: ${dayLabel(day)}`}
        info="Open-Meteo, архив погоды для центра Москвы по часам. На лидерборде поправка на погоду ухудшила скор на 0,26 п. п., поэтому в прогнозе по умолчанию она выключена; включить можно на вкладке «Сценарий».">
        <MiniLine values={w.temp[day] ?? []} labels={HOURS} color="#ffb547" mark={hour} format={(v) => fmtTemp(v)} />
        <MiniBars values={(w.precip[day] ?? []).map((v) => v ?? 0)} labels={HOURS} color="#7cc0ff" mark={hour} height={46} />
        <p className={styles.note}>Температура по часам и осадки, мм/ч. Эффект на посадки по истории 2025 года: −0,74 % на мм осадков за день.</p>
      </Card>

      <Card title="Погода за горизонт" info="Средняя температура суток и сумма осадков. Клик по дню недоступен здесь: выбирайте день в календаре сверху или в тепловой карте снизу.">
        <MiniLine values={dailyTemp} labels={w.dates.map(shortDate)}
          color="#ffb547" mark={day} format={(v) => fmtTemp(v)} />
        <MiniBars values={dailyPrecip} color="#7cc0ff" mark={day} height={40} />
      </Card>

      <Card title="Календарь горизонта"
        info="Производственный календарь 2025 (постановление № 1335, isdayoff.ru). Праздник в будний день прогнозируется как воскресенье ×0,95, рабочая суббота 1 ноября ×0,85 к будню, 29-30 декабря ×0,85, 31 декабря днём ×0,9 и ноль после 20:00: бесплатный проезд.">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(61, 1fr)', gap: 1 }}>
          {factors.calendar.map((c, i) => (
            <button key={c.date} type="button" title={`${c.date}${c.holiday ? `, ${c.holiday}` : ''}`}
              onClick={() => setDay(i)}
              style={{ height: 20, borderRadius: 2, background: c.holiday ? DAY_COLORS.holiday
                : !c.day_off && c.dow === 5 ? '#ffb547' : DAY_COLORS[c.day_type] ?? '#1f2c3d',
              outline: i === day ? '1.5px solid #fff' : 'none' }} />
          ))}
        </div>
        <ul className={styles.list}>
          {holidays.map((c) => <li key={c.date}><span>{shortDate(c.date)} - {c.holiday}</span></li>)}
          <li><span>01.11 - рабочая суббота перед тремя выходными</span></li>
        </ul>
      </Card>

      <Card title="Загруженность дорог"
        info="data.mos.ru, набор 62525: средний балл пробок по месяцам. Рост на 1 балл сопровождается ростом посадок трамвая Москвы на 10,5 % (p = 0,0001). Вес трафика в уровне ноября-декабря настраивается на вкладке «Сценарий».">
        <MiniBars values={traffic.score} labels={traffic.months}
          color="#b98cff" highlight={(i) => (traffic.months[i] ?? '') >= '2025-11' && (traffic.months[i] ?? '') <= '2025-12'} />
        <p className={styles.note}>Ноябрь-декабрь 2025 выделены: {traffic.score.slice(-2).map((v) => fmt1(v)).join(' и ')} балла.</p>
      </Card>

      <Card title="Трамвай Москвы по месяцам"
        info="data.mos.ru, набор 62521: посадки в сутки по всем трамвайным маршрутам города. Из отношения месяцев прошлых лет к октябрю строится уровень ноября и декабря (амплитуда наших маршрутов 0,83) и годовой прогноз.">
        <MiniLine values={city.per_day.slice(cityFrom)} labels={city.months.slice(cityFrom)}
          color="#3ddc97" mark={city.months.indexOf('2025-11') - cityFrom} format={(v) => fmtCompact(v)} />
        <p className={styles.note}>Отметка - ноябрь 2025. {monthLabel(city.months[city.months.length - 1] ?? '2026-08')}: {fmtCompact(city.per_day[city.per_day.length - 1])} посадок в сутки.</p>
      </Card>

      {sched && (
        <Card title={`Интервал движения: маршрут ${route ?? 17}`}
          info={`${factors.schedule.source}, выгрузка ${factors.schedule.fetched_at}. Это действующее расписание, а не расписание ноября 2025: используем его как оценку числа рейсов в час.`}>
          <MiniBars values={(sched.weekday?.headway_min ?? []).map((v) => v ?? 0)} labels={HOURS} color={routeColor(route ?? 17)} mark={hour} />
          <p className={styles.note}>Будни: работает {sched.weekday?.service_from}-{sched.weekday?.service_to}, выходные:
            {' '}{sched.weekend?.service_from}-{sched.weekend?.service_to}. Столбик - интервал в минутах, выше - реже.{' '}
            <a href={sched.page} target="_blank" rel="noopener noreferrer">Страница маршрута</a></p>
        </Card>
      )}

      <Card title="События сети" info="Разбор постов Telegram-канала «Дептранс. Оперативно», mos.ru и sobyanin.ru. Возврат выходных 7 и 50 с 15.11 дал +1,16 п. п. на лидерборде, запуск маршрута 5 с 16.12 +0,41 п. п.">
        <ul className={styles.list}>
          {factors.events.map((e) => (
            <li key={`${e.start}-${e.description}`}>
              <span><b>{shortDate(e.start)}{e.end && e.end !== e.start ? `-${shortDate(e.end)}` : ''}</b> {e.description}</span>
              <small>{e.routes === 'all' ? 'все маршруты' : `маршруты ${e.routes.replaceAll(';', ', ')}`}
                {e.effect ? `; в данных: ${e.effect}` : ''}{' '}
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
