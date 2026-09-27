"""Экспорт каталога artifacts/ для сервиса: компоненты прогноза, ползунки, сеть, горизонты, manifest.

Сервис на Java модели не запускает, он читает эти файлы при старте, сверяет их с manifest.json
по sha256 и числу строк и пересчитывает прогноз по формуле export_components.recompute.
По умолчанию это конкурсный прогноз v25: формула s30/s32 с множителем до v25 в каждой ячейке,
см. export_components.calibration.
Контракт описан в docs/research/review_round1.md, п. 7.1, и docs/architecture/backend_brief.md.
Запуск: uv run python analysis/s40_export_artifacts.py (после s33, если обновлялся трафик)
"""

import dataclasses
import datetime as dt
import hashlib
import json
import subprocess

import numpy as np
import pandas as pd

import s10_forecast as s10
from common import FORECAST_END, FORECAST_START, ROOT, ROUTES, TEST_END
from export_context import build_factors, check as check_factors
from export_timeline import actuals_frame, check as check_timeline, outlook_frame, timeline_calendar
from export_gaps import build_gaps
from outlook_factors import build_outlook_factors
from export_components import (ROUTE5_SATURDAY, ROUTE5_SUNDAY, TARGET_SUBMISSION, build_components, recompute,
                               scenario_coefficients)
from export_horizons import backtest_frame, intervals_and_metrics, year_forecast
from export_network import build_stops, network_geojson
from export_news import build_news
from export_plan import check as check_plan, plan_frame, plan_quality
from s30_ex_ante import coefficients as ex_ante_coefficients
from s34_traffic_probe import city_tram_monthly, novdec_levels

OUT = ROOT / "artifacts"
GOLDEN = OUT / "golden"
DEFAULT_SUBMISSION = TARGET_SUBMISSION
LEADERBOARD_SCORE = 0.91274  # Предположительная привязка скриншота к v25; порядок v25/v26 не подтверждён.
MODEL_VERSION = "final_feedback_v25"
SCHEMA_VERSION = 1


def default_coefficients() -> s10.Coefficients:
    return dataclasses.replace(ex_ante_coefficients(), route5_on=True)  # s32


def slider(key: str, label: str, group: str, kind: str, default, source: str, **extra) -> dict:
    return {"key": key, "label": label, "group": group, "type": kind, "default": default, **extra, "source": source}


def coefficient_catalog(c: s10.Coefficients, traffic: dict) -> dict:
    lb = "на проверке организаторов 25.09.2026 точность"
    items = [
        slider("level_nov", "Спрос в ноябре к октябрю", "level", "number", c.level_nov,
               "data.mos.ru, набор 62521: как менялись поездки на городском трамвае от октября к ноябрю "
               "в 2019 и 2022-2024 годах", min=0.8, max=1.2, step=0.001),
        slider("level_dec", "Спрос в декабре к октябрю", "level", "number", c.level_dec,
               "data.mos.ru, набор 62521: как менялись поездки на городском трамвае от октября к декабрю "
               "в 2019 и 2022-2024 годах", min=0.8, max=1.2, step=0.001),
        slider("traffic_weight", "Доля пробок в уровне спроса", "level", "number", 0.0,
               "data.mos.ru, набор 62525: +10,5 % посадок на балл пробок. 0 - уровень только по сезонности, "
               "1 - только по пробкам. Организаторы этот вариант не проверяли", min=0.0, max=1.0, step=0.05),
        slider("holiday_to_sunday", "Праздник в будний день как доля воскресенья", "calendar", "number",
               c.holiday_to_sunday, "праздники 2025 года, постановление Правительства РФ № 1335", min=0.6, max=1.2,
               step=0.01),
        slider("working_saturday", "Рабочая суббота 1 ноября как доля будня", "calendar", "number", c.working_saturday,
               "постановление Правительства РФ № 1335, рабочие субботы 2025 года", min=0.6, max=1.2, step=0.01),
        slider("last_workdays_dec", "29-30 декабря как доля будня", "calendar", "number", c.last_workdays_dec,
               "экспертная оценка: перед Новым годом ездят меньше", min=0.5, max=1.2, step=0.01),
        slider("dec31_day", "31 декабря днём как доля праздника", "calendar", "number", c.dec31_day,
               "как ездили 31.12.2024", min=0.5, max=1.2, step=0.01),
        slider("dec31_free_from_hour", "Бесплатный проезд 31 декабря с часа (24 - без бесплатного)", "events",
               "integer",
               c.dec31_free_from_hour, "mos.ru 25.12.2024, РБК 28.12.2023: бесплатная новогодняя ночь с 20:00",
               min=0, max=24, step=1),
        slider("weekend_restore_date", "Маршруты 7 и 50 по выходным снова по всей трассе с", "events", "date",
               c.weekend_restore_date, f"Дептранс, t.me/DtOperativno/23364; {lb} +1,16 п. п.",
               min=FORECAST_START, max="2026-01-01"),
        slider("t1_start", "Запуск трамвайного диаметра Т1", "events", "date", c.t1_start,
               "Дептранс, t.me/DtOperativno/23513: Т1 запущен 12.11.2025",
               min=FORECAST_START, max="2026-01-01"),
        slider("t1_route7", "Маршрут 7 после запуска Т1 как доля прежнего", "events", "number", c.t1_route7,
               "Т1 идёт общим участком с 7-м; по замеру на проверке организаторов поток №7 в декабре на 8 % ниже v11; "
               "в прогнозе по умолчанию не используется",
               min=0.7, max=1.1, step=0.01),
        slider("route5_on", "Маршрут 5 работает", "events", "boolean", c.route5_on,
               f"mos.ru, запуск 16.12.2025; {lb} +0,41 п. п."),
        slider("route5_start", "Запуск маршрута 5", "events", "datetime", c.route5_start.replace(" ", "T"),
               "mos.ru: маршрут 5 открыт 16.12.2025 вечером", min=f"{FORECAST_START}T00:00", max="2026-01-01T00:00"),
        slider("route5_workday", "Посадок маршрута 5 в будний день", "events", "number", c.route5_workday,
               "около 160 тыс. поездок за первый месяц работы", min=0, max=20000, step=100),
        slider("weather", "Учитывать фактическую погоду", "weather", "boolean", c.weather,
               f"Open-Meteo; {lb} -0,26 п. п., поэтому по умолчанию выключена"),
        slider("precip_day_coef", "Осадки за день: поправка на 1 мм (-0,01 = -1 %)", "weather", "number",
               c.precip_day_coef, "история 2025 года: -0,74 % посадок на 1 мм осадков за 6-22 ч",
               min=-0.05, max=0.0, step=0.0001),
        slider("hour_precip_coef", "Осадки в этот час: поправка на 1 мм, до 3 мм", "weather", "number",
               c.hour_precip_coef, "история 2025 года по часам", min=-0.1, max=0.0, step=0.001),
        slider("frost_coef", "Мороз ниже -10 °C: поправка на градус", "weather", "number", c.frost_coef,
               "история 2025 года, оценка по двум морозным дням", min=-0.05, max=0.0, step=0.0001),
    ]
    return {"schema_version": SCHEMA_VERSION, "scenario": MODEL_VERSION, "coefficients": items,
            "constants": {"traffic_level_nov": traffic["traffic_level_nov"],
                          "traffic_level_dec": traffic["traffic_level_dec"],
                          "route5_saturday_ratio": ROUTE5_SATURDAY, "route5_sunday_ratio": ROUTE5_SUNDAY},
            "groups": {"level": "Уровень", "calendar": "Календарь", "events": "События сети", "weather": "Погода"}}


def golden_scenarios(comp: pd.DataFrame, default: s10.Coefficients) -> tuple[pd.DataFrame, dict]:
    """Прогноз исходной реализацией s10 на наборах коэффициентов, с тем же множителем до v25: сервис
    обязан совпасть с ним."""
    table = comp[["route", "date", "hour"]].copy()
    sets = {}
    for name, c in scenario_coefficients(default).items():
        table[name] = s10.make_forecast(c).prediction.to_numpy() * comp.calib.to_numpy()
        changed = {k: v for k, v in dataclasses.asdict(c).items() if v != getattr(default, k) or name == "default"}
        if "route5_start" in changed:
            changed["route5_start"] = changed["route5_start"].replace(" ", "T")
        changed.pop("profile_weeks", None)  # база профиля в компонентах одна, это не ползунок
        sets[name] = changed
    return table, sets


def sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha256(path) -> str:
    """sha256 текста с концами строк LF: сабмит в forecasts/ git на Windows выдаёт с CRLF."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def git_commit() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def write_csv(df: pd.DataFrame, name: str) -> None:
    df.to_csv(OUT / name, index=False, lineterminator="\n")


def write_text(path, content: str) -> None:
    """Keep the checked-in artifact's line endings so rebuilds produce focused diffs."""
    if path.exists():
        old = path.read_bytes()
        if b"\r\n" in old and old.count(b"\r\n") == old.count(b"\n"):
            content = content.replace("\n", "\r\n")
    path.write_bytes(content.encode("utf-8"))


def write_json(obj: dict, name: str) -> None:
    write_text(OUT / name, json.dumps(obj, ensure_ascii=False, indent=1) + "\n")


def main() -> None:
    GOLDEN.mkdir(parents=True, exist_ok=True)
    c = default_coefficients()
    comp = build_components(c)
    pred = recompute(comp, c)
    sub = pd.read_csv(DEFAULT_SUBMISSION, sep=";")
    if not np.array_equal(np.round(pred).astype(int), sub.prediction.to_numpy()):
        raise ValueError(f"компоненты не воспроизводят {DEFAULT_SUBMISSION.name}")
    write_csv(comp.assign(prediction=pred), "forecast_components.csv")

    traffic = novdec_levels(city_tram_monthly())
    write_json(coefficient_catalog(c, traffic), "coefficients.json")

    stops, route_stops, stop_stats = build_stops()
    write_csv(stops, "stops.csv")
    write_csv(route_stops, "route_stops.csv")
    write_json(network_geojson(stops), "network.geojson")

    intervals, metrics = intervals_and_metrics(backtest_frame())
    year, year_meta = year_forecast(comp, pred)
    write_json(intervals, "intervals.json")
    write_csv(year, "forecast_year.csv")

    cal = timeline_calendar()
    actuals, equipment_checks = actuals_frame()
    gaps = build_gaps(actuals, cal)
    outlook_factors = build_outlook_factors(actuals, cal, gaps["periods"], ROUTES, c.precip_day_coef, c.frost_coef)
    outlook = outlook_frame(comp, pred, year, cal, outlook_factors)
    check_timeline(cal, actuals, outlook, year)
    write_csv(cal, "timeline_calendar.csv")
    write_csv(actuals, "actuals.csv")
    write_csv(outlook, "outlook.csv")
    plan = plan_frame()
    check_plan(plan, ROUTES)
    write_csv(plan, "plan.csv")
    write_json({**metrics, "leaderboard_wape_score": LEADERBOARD_SCORE,
                "leaderboard_score_attribution": "tentative_v25_v26_order", "year": year_meta, "stops": stop_stats,
                "plan": plan_quality(plan, actuals)}, "backtest_metrics.json")

    factors = {**build_factors(), "equipment_checks": equipment_checks, "gaps": gaps}
    check_factors(factors)
    write_text(OUT / "factors.json", json.dumps(factors, ensure_ascii=False, separators=(",", ":")) + "\n")

    write_json(build_news(), "news.json")

    table, sets = golden_scenarios(comp, c)
    table.to_csv(GOLDEN / "scenarios.csv", index=False, lineterminator="\n")
    write_text(GOLDEN / "scenarios.json", json.dumps(sets, ensure_ascii=False, indent=1) + "\n")

    files = ["forecast_components.csv", "coefficients.json", "stops.csv", "route_stops.csv", "network.geojson",
             "intervals.json", "forecast_year.csv", "backtest_metrics.json", "factors.json",
             "timeline_calendar.csv", "actuals.csv", "outlook.csv", "plan.csv", "news.json"]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "git_commit": git_commit(),
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "forecast_origin": TEST_END,
        "horizon": {"from": FORECAST_START, "to": FORECAST_END},
        "routes": ROUTES,
        "default_scenario": {"name": MODEL_VERSION, "script": "analysis/s121_final_two_submissions.py",
                             "formula": "analysis/s32_ex_ante_route5.py × calib до v25",
                             "submission": "forecasts/submission_final_feedback_v25.csv",
                             "submission_sha256_lf": text_sha256(DEFAULT_SUBMISSION),
                             "leaderboard_wape_score": LEADERBOARD_SCORE,
                             "score_attribution": "tentative: 0.91274 is assumed to belong to v25; v25/v26 upload order awaits confirmation"},
        "files": {name: {"sha256": sha256(OUT / name),
                         "rows": sum(1 for _ in (OUT / name).open(encoding="utf-8")) - 1 if name.endswith(".csv") else None}
                  for name in files},
        "outlook": {"from": "2026-01-01", "to": "2027-12-31", "method": "seasonal_index",
                    "note": "Сезонная оценка без тренда роста; точность 2027 и покрытие коридора ±12 % не проверены"},
    }
    write_json(manifest, "manifest.json")
    print(f"artifacts: {len(comp)} ячеек, сумма {pred.sum():,.0f}, совпадает с {DEFAULT_SUBMISSION.name}; "
          f"остановок {stop_stats['stops']}, OSM к справочнику {stop_stats['osm_matched_to_reference']}/"
          f"{stop_stats['osm_stops']}; покрытие коридора {metrics['interval_coverage_leave_one_fold_out']}")


if __name__ == "__main__":
    main()
