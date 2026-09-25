"""Файлы для проверки на лидерборде: каждый отличается от основного одной вещью.

Основа - blend_external (s10). Пробы отвечают на вопросы: есть ли маршрут 5 в эталоне,
куда сдвинут уровень (WAPE выпукла по множителю k, поэтому хватает нескольких точек),
и дают ли эффект отдельные внешние факторы (для критерия 2).
Запуск: uv run python analysis/s19_probes.py
"""

import dataclasses

import pandas as pd

from common import ROOT
from s10_forecast import VARIANTS, make_forecast, to_submission

OUT = ROOT / "forecasts" / "probes"
MAIN_COEFS, MAIN_MIX = VARIANTS["blend_external"]

# имя файла -> (коэффициенты, множитель уровня, что проверяем)
PROBES = {
    "p01_main": (MAIN_COEFS, 1.00, "основной вариант, точка отсчёта"),
    "p02_route5": (dataclasses.replace(MAIN_COEFS, route5_on=True), 1.00, "есть ли маршрут 5 в эталоне с 16.12"),
    "p03_level_x1.03": (MAIN_COEFS, 1.03, "уровень выше на 3 %"),
    "p04_level_x0.97": (MAIN_COEFS, 0.97, "уровень ниже на 3 %"),
    "p05_level_x1.06": (MAIN_COEFS, 1.06, "уровень выше на 6 %, если p03 лучше p01"),
    "p06_level_x0.94": (MAIN_COEFS, 0.94, "уровень ниже на 6 %, если p04 лучше p01"),
    "p07_no_weekend_restore": (dataclasses.replace(MAIN_COEFS, weekend_restore_date="2099-01-01"), 1.00,
                               "без восстановления выходных 7 и 50 с 15.11 (эффект новостей Дептранса)"),
    "p08_no_weather": (dataclasses.replace(MAIN_COEFS, weather=False), 1.00, "без погодных поправок"),
    "p09_no_calendar_rules": (dataclasses.replace(MAIN_COEFS, working_saturday=1.0, last_workdays_dec=1.0,
                                                  dec31_day=1.0, dec31_free_from_hour=24), 1.00,
                              "без правил 01.11, 29-31.12 и нуля после 20:00 31.12"),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    cache: dict = {}
    for name, (coefs, k, question) in PROBES.items():
        key = dataclasses.astuple(coefs)
        if key not in cache:
            cache[key] = make_forecast(coefs, MAIN_MIX)
        fc = cache[key].assign(prediction=cache[key].prediction * k)
        sub = to_submission(fc, OUT / f"{name}.csv")
        rows.append({"file": f"{name}.csv", "question": question, "total": int(sub.prediction.sum())})
        print(f"{name:26s} total={rows[-1]['total']:,}  {question}")
    pd.DataFrame(rows).to_csv(OUT / "probes_index.csv", index=False)


if __name__ == "__main__":
    main()
