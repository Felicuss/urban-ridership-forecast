# Внешние данные

Всё, что не пришло от организаторов. Автоматические выгрузки повторяются скриптами `analysis/s01_fetch_weather.py` и `analysis/s08_fetch_external.py`, ручные таблицы собраны по первоисточникам со ссылками в каждой строке. Как каждый источник влияет на посадки, описано в [docs/analysis/README.md](../docs/analysis/README.md), п. 3.

| Файл | Что внутри | Источник | Как получить | Лицензия |
|---|---|---|---|---|
| `weather_moscow_2025_hourly.csv` | Почасовая погода центра Москвы за 2025 год: температура, ощущаемая температура, осадки, дождь, снегопад, высота снега, код погоды, облачность, ветер | [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) | `GET https://archive-api.open-meteo.com/v1/archive?latitude=55.7558&longitude=37.6173&start_date=2025-01-01&end_date=2025-12-31&hourly=...&timezone=Europe/Moscow` | CC BY 4.0, бесплатно для некоммерческого использования |
| `daylight_moscow_2025.csv` | Восход, закат, световой день | Open-Meteo, тот же API, `daily=sunrise,sunset,daylight_duration` | см. `s08_fetch_external.py` | CC BY 4.0 |
| `production_calendar_{2019,2022,2023,2024,2025}_isdayoff.csv` | Производственный календарь: 0 рабочий, 1 выходной, 2 сокращённый, 8 праздник | [isdayoff.ru](https://isdayoff.ru/docs/), сверено с [постановлением № 1335](https://www.consultant.ru/law/ref/calendar/proizvodstvennye/2025/) | `GET https://isdayoff.ru/api/getdata?year=2025&cc=ru&pre=1&holiday=1` | не указана |
| `datamos_62521_monthly_ridership.csv` | Месячный пассажиропоток по видам транспорта Москвы с января 2019 года | [data.mos.ru, набор 62521](https://data.mos.ru/opendata/7704786030-mesyachniy-passajiropotok-po-vsem-vidam-obshchestvennogo-transporta-v-gorode-moskve) | `POST https://data.mos.ru/api/v2/odata/catalog/get` с телом `{"id":114682,"epoch":"2026-09-15 15:00:47","timestamp":1,"criteria":""}` | открытые данные Правительства Москвы |
| `osm_tram_routes.geojson` | Трассы (линии путей) и остановки маршрутов 1, 5, 7, 11, 12, 17, 25, 26, 28, 50, по два направления | [OpenStreetMap](https://www.openstreetmap.org/), Overpass API | запрос `relation["route"="tram"]["ref"~"^(1|5|...)$"](bbox); out geom;` с заголовком `Accept: application/json` | ODbL 1.0, © OpenStreetMap contributors |
| `school_holidays_moscow.csv` | Школьные каникулы Москвы 2024/25 и 2025/26 | графики школ на mskobr.ru, ссылки в файле | вручную | - |
| `events_2025.csv` | Перекрытия, изменения трасс, запуски маршрутов, бесплатный проезд, аномалии данных за 2025 год | Telegram-канал [«Дептранс. Оперативно»](https://t.me/DtOperativno), mos.ru, sobyanin.ru; ссылка на пост в каждой строке | вручную, по разбору 5273 постов | - |

Дорожного трафика здесь нет: открытого архива загруженности Москвы за 2025 год не существует. Что проверено и почему не подошло, описано в [docs/research/external_sources.md](../docs/research/external_sources.md), п. 4.
