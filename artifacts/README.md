# Артефакты для сервиса

Сервис модель не запускает. При старте он читает эти файлы, сверяет каждый с `manifest.json` по sha256 и числу строк и дальше считает прогноз по формуле ниже. Собирает каталог `analysis/s40_export_artifacts.py`, проверяет `tests/test_artifacts.py`:

```
uv run python analysis/s40_export_artifacts.py
uv run pytest
```

По умолчанию каталог воспроизводит лучший сабмит `forecasts/submission_ex_ante_route5.csv` (0.89950 на лидерборде) во всех 14 640 ячейках.

| Файл | Что внутри |
|---|---|
| `manifest.json` | версия схемы, коммит, дата прогноза 31.10.2025, горизонт, sha256 и число строк файлов, сабмит по умолчанию |
| `forecast_components.csv` | ячейка маршрут × дата × час: календарные флаги, база профиля, база выходных 7 и 50 по полной трассе, форма суток маршрута 5, погода, прогноз по умолчанию |
| `coefficients.json` | ползунки: ключ, подпись, группа, тип, значение по умолчанию, диапазон, шаг, источник; константы трафика и маршрута 5 |
| `stops.csv`, `route_stops.csv` | остановки (справочник для 1, 5, 7, 11, 12, OSM для остальных) и доли посадок маршрута по остановкам, сумма долей маршрута 1 |
| `network.geojson` | трассы по направлениям и остановки для карты |
| `intervals.json` | множители коридора p10-p90 по часу суток, типу дня и для месяца |
| `forecast_year.csv` | помесячный прогноз ноябрь 2025 - октябрь 2026 с коридором ±12 % |
| `backtest_metrics.json` | WAPE-score схемы на пяти фолдах по часам, суткам и месяцам, покрытие коридора, проверка годового индекса |
| `golden/` | прогноз исходной реализации s10 на пяти наборах коэффициентов, эталон для тестов сервиса |

## Формула

Для ячейки маршрута r, даты d и часа h, коэффициенты берутся из `coefficients.json` или из запроса:

```
level      = level_m^(1 - traffic_weight) × traffic_level_m^traffic_weight      (m - ноябрь или декабрь)
restored   = restorable и d >= weekend_restore_date
base       = restored ? base_restored × level × holiday_to_sunday^[is_holiday]
                      : base × level × holiday_to_sunday^[is_holiday и будний день]
                             × working_saturday^[is_working_saturday] × last_workdays_dec^[is_pre_new_year]
pred       = base × dec31_day^[is_new_year_eve] × t1_route7^[r = 7 и d >= t1_start]
pred       = 0, если is_new_year_eve и h >= dec31_free_from_hour
маршрут 5:  pred = route5_on и (d, h) >= route5_start ? route5_workday × route5_shape × k : 0,
            k = 0.6 в субботу, 0.5 в воскресенье и праздник, иначе 1; ноль после dec31_free_from_hour 31.12
погода:     pred × exp(precip_day_coef × precip_day + hour_precip_coef × min(precip_hour, 3)
                       + frost_coef × max(-10 - temp_day, 0)), если weather
```

Доли по остановкам - оценка: остановки посадки в валидациях нет. Как они считаются, описано в `analysis/export_network.py`.
