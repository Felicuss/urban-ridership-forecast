"""Кандидат в лучший сабмит: честный вариант s30 + маршрут 5 с 16.12.

Организаторы 25.09.2026 разрешили внешние данные, опубликованные после 31.10, а скор
на лидерборде считается по всему ноябрю-декабрю без скрытой части. Из постфактум-фактов
на лидерборде подтвердился маршрут 5 (+0.41 п.п. к смеси), а база s30 оказалась лучше
смеси (0.89541 против 0.89431 у p08 при тех же выключенных маршруте 5 и погоде).
Здесь база s30 и маршрут 5, остальное как в s30.
Запуск: uv run python analysis/s32_ex_ante_route5.py
"""

import dataclasses
import json

import pandas as pd

import s10_forecast as s10
from s30_ex_ante import coefficients


def main() -> None:
    coefs = dataclasses.replace(coefficients(), route5_on=True)
    fc = s10.make_forecast(coefs)
    sub = s10.to_submission(fc, s10.OUT / "submission_ex_ante_route5.csv")
    meta = {"base": "s30 ex-ante", "added": "маршрут 5 с 16.12 18:00", **dataclasses.asdict(coefs)}
    (s10.OUT / "coefficients_ex_ante_route5.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                                             encoding="utf-8")
    base = pd.read_csv(s10.OUT / "submission_ex_ante.csv", sep=";")
    diff = sub.prediction != base.prediction
    print(f"отличается от submission_ex_ante: {diff.sum()} строк, маршруты {sorted(sub.route[diff].unique())}, "
          f"+{int((sub.prediction - base.prediction).sum()):,} посадок; итого {int(sub.prediction.sum()):,}")


if __name__ == "__main__":
    main()
