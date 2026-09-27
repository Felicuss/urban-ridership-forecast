"""Пересборка только artifacts/outlook.csv (оценка января-октября 2026) из готовых артефактов.

Полный s40_export_artifacts.py требует исходных данных организаторов; этот скрипт берёт то, что уже лежит
в artifacts/: forecast_components.csv (прогноз ноября-декабря 2025 для формы суток), forecast_year.csv,
timeline_calendar.csv, actuals.csv, factors.json (пропуски факта), coefficients.json (погода), и погоду 2026
из external/weather_moscow_2026_daily.csv. После проверки check обновляет в manifest.json sha256 и число
строк outlook.csv, остальное в манифесте не трогает.
Запуск: uv run python analysis/export_outlook.py
"""

import hashlib
import json

import pandas as pd

from common import ROOT, ROUTES
from export_timeline import check, outlook_frame
from outlook_factors import OutlookFactors, build_outlook_factors

OUT = ROOT / "artifacts"
NAME = "outlook.csv"
EVIDENCE = (("17", "2026-03"), ("26", "2026-10"))


def coefficient(catalog: dict, key: str) -> float:
    return float(next(c["default"] for c in catalog["coefficients"] if c["key"] == key))


def load_factors(actuals: pd.DataFrame, cal: pd.DataFrame) -> OutlookFactors:
    catalog = json.loads((OUT / "coefficients.json").read_text(encoding="utf-8"))
    gaps = json.loads((OUT / "factors.json").read_text(encoding="utf-8"))["gaps"]["periods"]
    return build_outlook_factors(actuals, cal, gaps, ROUTES, coefficient(catalog, "precip_day_coef"),
                                 coefficient(catalog, "frost_coef"))


def update_manifest() -> None:
    path = OUT / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    target = OUT / NAME
    manifest["files"][NAME] = {"sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                               "rows": sum(1 for _ in target.open(encoding="utf-8")) - 1}
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def report(factors: OutlookFactors, outlook: pd.DataFrame) -> None:
    print("профиль дня недели (Пн-Пт к среднему будню):")
    print(factors.weekday.round(3).to_string())
    print(f"школьные каникулы, будень к обычному: {factors.school_break:.4f} по сети; по маршрутам:")
    print(factors.school_by_route.round(3).to_string())
    print(f"погода: {factors.precip_day_coef} на 1 мм осадков 6-22 ч, {factors.frost_coef} на градус ниже -10 °C; "
          f"дней с погодой {len(factors.weather)}, множитель от {factors.weather.min():.3f} до "
          f"{factors.weather.max():.3f}")
    daily = outlook.groupby(["route", "date"]).p50.sum().round(1)
    for route, month in EVIDENCE:
        part = daily.loc[int(route)]
        print(f"маршрут {route}, {month}:")
        print(part[part.index.str.startswith(month)].to_string())


def main() -> None:
    comp = pd.read_csv(OUT / "forecast_components.csv")
    year = pd.read_csv(OUT / "forecast_year.csv")
    cal = pd.read_csv(OUT / "timeline_calendar.csv")
    actuals = pd.read_csv(OUT / "actuals.csv")
    factors = load_factors(actuals, cal)
    outlook = outlook_frame(comp, comp.prediction.to_numpy(), year, cal, factors)
    check(cal, actuals, outlook, year)
    outlook.to_csv(OUT / NAME, index=False, lineterminator="\n")
    update_manifest()
    report(factors, outlook)


if __name__ == "__main__":
    main()
