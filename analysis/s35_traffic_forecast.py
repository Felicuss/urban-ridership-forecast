"""Вариант прогноза с уровнем по загруженности дорог: s32 + трафик (data.mos.ru 62525).

На бэктесте s34 уровень по трафику улучшает профиль на всех пяти фолдах, а в смеси с
сезонностью прошлых лет (схема s30) даёт 0.8724 против 0.8683. Здесь та же смесь на
ноябре-декабре 2025: уровень s30 и уровень по трафику усредняются в логарифме с весом
TRAFFIC_WEIGHT. Загруженность за ноябрь-декабрь 2025 опубликована постфактум, такие данные
организаторы разрешили. Остальное как в s32: маршрут 5 с 16.12, без Т1 и погоды.
Запуск: uv run python analysis/s35_traffic_forecast.py (после s33)
"""

import dataclasses
import json

import numpy as np
import pandas as pd

import s10_forecast as s10
from common import load_labels
from s30_ex_ante import coefficients
from s34_traffic_probe import city_tram_monthly, novdec_levels

TRAFFIC_WEIGHT = 0.5  # ползунок в сервисе: 0 - уровень s30, 1 - только трафик


def mix_level(seasonal: float, traffic: float) -> float:
    return round(float(np.exp((1 - TRAFFIC_WEIGHT) * np.log(seasonal) + TRAFFIC_WEIGHT * np.log(traffic))), 4)


def main() -> None:
    base = dataclasses.replace(coefficients(), route5_on=True)  # s32
    traffic = novdec_levels(city_tram_monthly())
    coefs = dataclasses.replace(base, level_nov=mix_level(base.level_nov, traffic["traffic_level_nov"]),
                                level_dec=mix_level(base.level_dec, traffic["traffic_level_dec"]))
    fc = s10.make_forecast(coefs)
    sub = s10.to_submission(fc, s10.OUT / "submission_traffic.csv")
    meta = {"base": "s32 (s30 ex-ante + маршрут 5)",
            "added": "уровень ноября-декабря: смесь уровня s30 и уровня по загруженности дорог data.mos.ru 62525",
            "traffic_weight": TRAFFIC_WEIGHT, "seasonal_level_nov": base.level_nov, "seasonal_level_dec": base.level_dec,
            **traffic, **dataclasses.asdict(coefs)}
    (s10.OUT / "coefficients_traffic.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    labels = load_labels()
    oct_day = labels[labels.date.dt.month == 10].boardings.sum() / 31
    ref = pd.read_csv(s10.OUT / "submission_ex_ante_route5.csv", sep=";")
    month = pd.to_datetime(sub.date).dt.month
    print(f"уровень к октябрю: s32 {base.level_nov} / {base.level_dec}, трафик {traffic['traffic_level_nov']} / "
          f"{traffic['traffic_level_dec']}, смесь {coefs.level_nov} / {coefs.level_dec}")
    for m, days in ((11, 30), (12, 31)):
        new, old = sub.prediction[month == m].sum(), ref.prediction[month == m].sum()
        print(f"месяц {m}: {new:,.0f} ({new / days / oct_day:.3f} к октябрю в сутки), s32 {old:,.0f}, {new / old - 1:+.1%}")


if __name__ == "__main__":
    main()
