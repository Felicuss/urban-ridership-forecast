"""Честный прогноз от 31.10.2025: только то, что было известно на дату прогноза.

Основной вариант s10 опирается на факты, опубликованные позже: data.mos.ru за
ноябрь-декабрь 2025, пост о возврате выходных 7 и 50 от 15.11, даты Т1 и маршрута 5,
фактическую погоду. Здесь каждый такой фактор либо заменён тем, что знали 31.10,
либо выключен. Таблица «фактор — что известно на 31.10 — источник» пишется рядом с
сабмитом, чтобы её можно было показать жюри.

База — профиль за 2 недели без foundation-моделей: он собирается из репозитория без
кэша FM и лучше профиля за 4 недели на всех трёх 61-дневных фолдах.
Запуск: uv run python analysis/s30_ex_ante.py
"""

import dataclasses
import json

import pandas as pd

import s10_forecast as s10
from common import ROOT, load_labels

# Медиана отношений 2019 и 2022-2024 (2020-2021 — ковид, 2025 — постфактум),
# амплитуда наших маршрутов к городскому трамваю 0.83, как в s10.
PAST_YEARS = [2019, 2022, 2023, 2024]
AMPLITUDE = 0.83

KNOWN_AT_ORIGIN = [
    ("уровень ноября и декабря", "отношения городского трамвая прошлых лет", "data.mos.ru 62521, 2019 и 2022-2024"),
    ("календарь 01.11, 03-04.11, 29-31.12", "постановление № 1335 от 04.10.2024", "isdayoff.ru, КонсультантПлюс"),
    ("ноль после 20:00 31.12", "бесплатная новогодняя ночь в 2023/24 и 2024/25 с 20:00", "mos.ru 25.12.2024, РБК 28.12.2023"),
    ("выходные 7 и 50 с 15.11", "маршруты закрыты по выходным из-за ремонта Протопоповского пер. (05.09); "
     "последние объявленные работы в переулке — до 04:30 10.11 (пост от 31.10 15:14)",
     "t.me/DtOperativno/22624, t.me/DtOperativno/23364"),
    ("Т1 и отток с маршрута 7", "выключено: 31.10 знали только «до конца 2025»", "mos.ru 10.09.2025"),
    ("маршрут 5", "выключено: ждали «конец октября — начало ноября» без даты и номера", "msknovosti 30.09.2025"),
    ("погода", "выключено: фактическая погода ноября-декабря на 31.10 неизвестна", "—"),
]


def ex_ante_levels() -> tuple[float, float]:
    city = pd.read_csv(ROOT / "external" / "datamos_62521_monthly_ridership.csv")
    tram = city[city.transport == "Трамвай"].pivot(index="year", columns="month", values="per_day").loc[PAST_YEARS]
    nov = 1 + AMPLITUDE * ((tram[11] / tram[10]).median() - 1)
    dec = 1 + AMPLITUDE * ((tram[12] / tram[10]).median() - 1)
    return round(nov, 4), round(dec, 4)


def coefficients() -> s10.Coefficients:
    level_nov, level_dec = ex_ante_levels()
    return dataclasses.replace(
        s10.Coefficients(), profile_weeks=2, level_nov=level_nov, level_dec=level_dec,
        weather=False, route5_on=False, t1_route7=1.0,
    )


def main() -> None:
    coefs = coefficients()
    level_nov, level_dec = coefs.level_nov, coefs.level_dec
    fc = s10.make_forecast(coefs)
    sub = s10.to_submission(fc, s10.OUT / "submission_ex_ante.csv")
    meta = {"origin": "2025-10-31", "past_years": PAST_YEARS, "amplitude": AMPLITUDE, **dataclasses.asdict(coefs),
            "known_at_origin": [dict(zip(("factor", "basis", "source"), row)) for row in KNOWN_AT_ORIGIN]}
    (s10.OUT / "coefficients_ex_ante.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    final = pd.read_csv(s10.OUT / "submission_final.csv", sep=";")
    labels = load_labels()
    oct_day = labels[labels.date.dt.month == 10].boardings.sum() / 31
    month = pd.to_datetime(sub.date).dt.month
    print(f"уровень ex-ante: ноябрь {level_nov}, декабрь {level_dec}")
    for m, days in ((11, 30), (12, 31)):
        ea, fin = sub.prediction[month == m].sum(), final.prediction[month == m].sum()
        print(f"месяц {m}: ex-ante {ea:,.0f} ({ea / days / oct_day:.3f} к октябрю в сутки), final {fin:,.0f}")
    print(f"сумма ex-ante {sub.prediction.sum():,.0f}, final {final.prediction.sum():,.0f}")


if __name__ == "__main__":
    main()
