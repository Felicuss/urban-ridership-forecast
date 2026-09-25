"""Экспорт каталога artifacts/ для сервиса: компоненты прогноза, ползунки, сеть, горизонты, manifest.

Сервис на Java модели не запускает, он читает эти файлы при старте, сверяет их с manifest.json
по sha256 и числу строк и пересчитывает прогноз по формуле export_components.recompute.
По умолчанию это лучший сабмит на лидерборде: s32 = честный вариант s30 + маршрут 5, 0.89950.
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
from export_components import ROUTE5_SATURDAY, ROUTE5_SUNDAY, build_components, recompute, scenario_coefficients
from export_horizons import backtest_frame, intervals_and_metrics, year_forecast
from export_network import build_stops, network_geojson
from s30_ex_ante import coefficients as ex_ante_coefficients
from s34_traffic_probe import city_tram_monthly, novdec_levels

OUT = ROOT / "artifacts"
GOLDEN = OUT / "golden"
DEFAULT_SUBMISSION = s10.OUT / "submission_ex_ante_route5.csv"
LEADERBOARD_SCORE = 0.8995
SCHEMA_VERSION = 1


def default_coefficients() -> s10.Coefficients:
    return dataclasses.replace(ex_ante_coefficients(), route5_on=True)  # s32


def slider(key: str, label: str, group: str, kind: str, default, source: str, **extra) -> dict:
    return {"key": key, "label": label, "group": group, "type": kind, "default": default, **extra, "source": source}


def coefficient_catalog(c: s10.Coefficients, traffic: dict) -> dict:
    lb = "проверено на лидерборде 25.09.2026"
    items = [
        slider("level_nov", "Уровень ноября к октябрю", "level", "number", c.level_nov,
               "data.mos.ru 62521: городской трамвай 2019 и 2022-2024, амплитуда 0.83", min=0.8, max=1.2, step=0.001),
        slider("level_dec", "Уровень декабря к октябрю", "level", "number", c.level_dec,
               "data.mos.ru 62521: городской трамвай 2019 и 2022-2024, амплитуда 0.83", min=0.8, max=1.2, step=0.001),
        slider("traffic_weight", "Вес загруженности дорог в уровне", "level", "number", 0.0,
               "data.mos.ru 62525: +10.5 % посадок на балл загруженности (s34); уровень = сезонный^(1-w) × трафик^w, "
               "на лидерборде не проверялся", min=0.0, max=1.0, step=0.05),
        slider("holiday_to_sunday", "Праздник в будний день к воскресенью", "calendar", "number", c.holiday_to_sunday,
               "история праздников 2025, постановление № 1335", min=0.6, max=1.2, step=0.01),
        slider("working_saturday", "Рабочая суббота 01.11 к будню", "calendar", "number", c.working_saturday,
               "постановление № 1335, рабочие субботы 2025", min=0.6, max=1.2, step=0.01),
        slider("last_workdays_dec", "29-30.12 к будню", "calendar", "number", c.last_workdays_dec,
               "экспертная оценка, предновогодние дни", min=0.5, max=1.2, step=0.01),
        slider("dec31_day", "31.12 днём к профилю праздника", "calendar", "number", c.dec31_day,
               "история 31.12.2024", min=0.5, max=1.2, step=0.01),
        slider("dec31_free_from_hour", "Бесплатный проезд 31.12 с часа (24 - нет)", "events", "integer",
               c.dec31_free_from_hour, "mos.ru 25.12.2024, РБК 28.12.2023: бесплатная новогодняя ночь с 20:00",
               min=0, max=24, step=1),
        slider("weekend_restore_date", "Выходные 7 и 50 снова по полной трассе с", "events", "date",
               c.weekend_restore_date, f"Дептранс, t.me/DtOperativno/23364; {lb}: +1.16 п.п.",
               min=FORECAST_START, max="2026-01-01"),
        slider("t1_start", "Запуск электробуса Т1", "events", "date", c.t1_start, "mos.ru 10.09.2025",
               min=FORECAST_START, max="2026-01-01"),
        slider("t1_route7", "Маршрут 7 после запуска Т1", "events", "number", c.t1_route7,
               "гипотеза, в честном варианте выключена", min=0.7, max=1.1, step=0.01),
        slider("route5_on", "Маршрут 5 работает", "events", "boolean", c.route5_on, f"mos.ru, запуск 16.12.2025; {lb}: +0.41 п.п."),
        slider("route5_start", "Запуск маршрута 5", "events", "datetime", c.route5_start.replace(" ", "T"),
               "mos.ru: маршрут 5 открыт 16.12.2025 вечером", min=f"{FORECAST_START}T00:00", max="2026-01-01T00:00"),
        slider("route5_workday", "Посадок маршрута 5 в будний день", "events", "number", c.route5_workday,
               "около 160 тыс. поездок за первый месяц", min=0, max=20000, step=100),
        slider("weather", "Учитывать фактическую погоду", "weather", "boolean", c.weather,
               f"Open-Meteo; {lb}: -0.26 п.п., поэтому по умолчанию выключена"),
        slider("precip_day_coef", "Осадки за день, log-эффект на мм", "weather", "number", c.precip_day_coef,
               "s05: -0.74 % посадок на мм осадков за 06-22 ч", min=-0.05, max=0.0, step=0.0001),
        slider("hour_precip_coef", "Осадки в этот час, log-эффект на мм (до 3 мм)", "weather", "number",
               c.hour_precip_coef, "s09", min=-0.1, max=0.0, step=0.001),
        slider("frost_coef", "Мороз ниже -10 °C, log-эффект на градус", "weather", "number", c.frost_coef,
               "s09, оценено по двум дням", min=-0.05, max=0.0, step=0.0001),
    ]
    return {"schema_version": SCHEMA_VERSION, "scenario": "ex_ante_route5", "coefficients": items,
            "constants": {"traffic_level_nov": traffic["traffic_level_nov"],
                          "traffic_level_dec": traffic["traffic_level_dec"],
                          "route5_saturday_ratio": ROUTE5_SATURDAY, "route5_sunday_ratio": ROUTE5_SUNDAY},
            "groups": {"level": "Уровень", "calendar": "Календарь", "events": "События сети", "weather": "Погода"}}


def golden_scenarios(comp: pd.DataFrame, default: s10.Coefficients) -> tuple[pd.DataFrame, dict]:
    """Прогноз исходной реализацией s10 на наборах коэффициентов: сервис обязан совпасть с ним."""
    table = comp[["route", "date", "hour"]].copy()
    sets = {}
    for name, c in scenario_coefficients(default).items():
        table[name] = s10.make_forecast(c).prediction.to_numpy()
        changed = {k: v for k, v in dataclasses.asdict(c).items() if v != getattr(default, k) or name == "default"}
        if "route5_start" in changed:
            changed["route5_start"] = changed["route5_start"].replace(" ", "T")
        changed.pop("profile_weeks", None)  # база профиля в компонентах одна, это не ползунок
        sets[name] = changed
    return table, sets


def sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def write_csv(df: pd.DataFrame, name: str) -> None:
    df.to_csv(OUT / name, index=False, lineterminator="\n")


def write_json(obj: dict, name: str) -> None:
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


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
    write_json({**metrics, "leaderboard_wape_score": LEADERBOARD_SCORE, "year": year_meta, "stops": stop_stats},
               "backtest_metrics.json")

    table, sets = golden_scenarios(comp, c)
    table.to_csv(GOLDEN / "scenarios.csv", index=False, lineterminator="\n")
    (GOLDEN / "scenarios.json").write_text(json.dumps(sets, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    files = ["forecast_components.csv", "coefficients.json", "stops.csv", "route_stops.csv", "network.geojson",
             "intervals.json", "forecast_year.csv", "backtest_metrics.json"]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_version": "ex_ante_route5",
        "git_commit": git_commit(),
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "forecast_origin": TEST_END,
        "horizon": {"from": FORECAST_START, "to": FORECAST_END},
        "routes": ROUTES,
        "default_scenario": {"name": "ex_ante_route5", "script": "analysis/s32_ex_ante_route5.py",
                             "submission": "forecasts/submission_ex_ante_route5.csv",
                             "submission_sha256": sha256(DEFAULT_SUBMISSION),
                             "leaderboard_wape_score": LEADERBOARD_SCORE},
        "files": {name: {"sha256": sha256(OUT / name),
                         "rows": sum(1 for _ in (OUT / name).open(encoding="utf-8")) - 1 if name.endswith(".csv") else None}
                  for name in files},
    }
    write_json(manifest, "manifest.json")
    print(f"artifacts: {len(comp)} ячеек, сумма {pred.sum():,.0f}, совпадает с {DEFAULT_SUBMISSION.name}; "
          f"остановок {stop_stats['stops']}, OSM к справочнику {stop_stats['osm_matched_to_reference']}/"
          f"{stop_stats['osm_stops']}; покрытие коридора {metrics['interval_coverage_leave_one_fold_out']}")


if __name__ == "__main__":
    main()
