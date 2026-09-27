"""Эталонные тесты каталога artifacts/: сервис считает по этим файлам, ошибка в них стоит баллов.

Запуск: uv run pytest
"""

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

import s10_forecast as s10
from export_components import build_components, recompute, scenario_coefficients
from s40_export_artifacts import DEFAULT_SUBMISSION, OUT, default_coefficients, text_sha256


@pytest.fixture(scope="module")
def components() -> pd.DataFrame:
    return pd.read_csv(OUT / "forecast_components.csv")


def test_components_reproduce_best_submission_in_every_cell(components):
    sub = pd.read_csv(DEFAULT_SUBMISSION, sep=";")
    pred = recompute(components, default_coefficients())

    assert len(components) == len(sub) == 14640
    assert (components[["route", "date", "hour"]].to_numpy() == sub[["route", "date", "hour"]].to_numpy()).all()
    assert np.array_equal(np.round(pred).astype(int), sub.prediction.to_numpy())
    np.testing.assert_allclose(components.prediction, pred, rtol=0, atol=1e-9)


@pytest.mark.parametrize("name", list(scenario_coefficients(s10.Coefficients())))
def test_formula_matches_original_rules_when_coefficients_move(components, name):
    """recompute повторяет s10.apply_rules не только в точке по умолчанию: иначе ползунки врут.
    Множитель до v11 в каждой ячейке один и тот же при любых коэффициентах."""
    c = scenario_coefficients(default_coefficients())[name]

    expected = s10.make_forecast(c).prediction.to_numpy() * components.calib.to_numpy()

    np.testing.assert_allclose(recompute(components, c), expected, rtol=1e-12, atol=1e-9)


def test_exported_components_are_fresh(components):
    """Файл собран из текущего кода и данных, а не остался от прошлой версии."""
    fresh = build_components(default_coefficients())

    pd.testing.assert_frame_equal(components.drop(columns="prediction"), fresh.reset_index(drop=True),
                                  check_exact=False, rtol=1e-12, check_dtype=False)


def test_manifest_matches_files():
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))

    for name, meta in manifest["files"].items():
        path = OUT / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == meta["sha256"], name
        if meta["rows"] is not None:
            assert sum(1 for _ in path.open(encoding="utf-8")) - 1 == meta["rows"], name
    assert text_sha256(DEFAULT_SUBMISSION) == manifest["default_scenario"]["submission_sha256_lf"]


def test_stop_shares_keep_route_total():
    rs = pd.read_csv(OUT / "route_stops.csv")
    stops = pd.read_csv(OUT / "stops.csv")

    by_route = rs.groupby("route").share.sum()
    np.testing.assert_allclose(by_route.to_numpy(), 1.0, atol=1e-12)
    assert sorted(by_route.index) == sorted(s10.ROUTES)
    last = rs.loc[rs.groupby(["route", "direction"]).seq.idxmax()]
    assert (last.share == 0).all(), "на конечной только выходят"
    assert set(rs.stop_id) <= set(stops.stop_id)


def test_timeline_fact_is_the_organizers_data_and_outlook_adds_up_to_the_year():
    from common import load_labels
    from export_timeline import check

    actuals = pd.read_csv(OUT / "actuals.csv")
    outlook = pd.read_csv(OUT / "outlook.csv")
    cal = pd.read_csv(OUT / "timeline_calendar.csv")
    year = pd.read_csv(OUT / "forecast_year.csv")
    labels = load_labels()

    # факт - метки организаторов, только проверки оборудования в нерабочие часы маршрута обнулены
    checks = json.loads((OUT / "factors.json").read_text(encoding="utf-8"))["equipment_checks"]
    labels = labels[labels.date <= "2025-10-31"].sort_values(["route", "date", "hour"])
    actuals = actuals.sort_values(["route", "date", "hour"])
    off = np.array([h in checks["off_hours"][str(r)] for r, h in zip(labels.route, labels.hour)])
    expected = np.where(off, 0, labels.boardings.to_numpy())
    assert np.array_equal(actuals.boardings.to_numpy(), expected)
    assert labels.boardings.sum() - actuals.boardings.sum() == checks["validations"]
    assert 0 < checks["share_pct"] < 0.01, "проверки оборудования - доли процента, не пассажиры"
    check(cal, actuals, outlook, year)
    assert cal[cal.date == "2026-01-09"].day_off.item(), "перенос выходного 2026 из производственного календаря"
    assert cal[cal.date == "2025-11-01"].day_type.item() == "workday", "рабочая суббота 1 ноября"


def test_gaps_name_the_reason_and_restore_from_earlier_weeks():
    """Пропуски факта: выходные №50 осенью 2025 - закрытие по посту Дептранса, восстановленные посадки
    по прошлым выходным на порядок больше факта; у каждого дня пропуска 24 восстановленных часа."""
    gaps = json.loads((OUT / "factors.json").read_text(encoding="utf-8"))["gaps"]
    by_route = {(p["route"], p["from"]): p for p in gaps["periods"]}
    autumn = by_route[(50, "2025-09-06")]
    assert autumn["type"] == "closure" and autumn["source"].startswith("https://t.me/DtOperativno/")
    assert autumn["restored"] > 10 * autumn["fact"]
    for p in gaps["periods"]:
        days = gaps["restored"][str(p["route"])]
        inside = [d for d in days if p["from"] <= d <= p["to"]]
        assert len(inside) == p["days"]
        assert all(len(days[d]) == 24 for d in inside)


def test_outlook_days_differ_inside_the_month_by_real_factors():
    """Жалоба диспетчеров: в оценке 2026 все будни месяца были равны. Теперь их различают день недели,
    школьные каникулы, погода и плавный уровень, а сумма месяца остаётся из сезонного индекса."""
    outlook = pd.read_csv(OUT / "outlook.csv")
    cal = pd.read_csv(OUT / "timeline_calendar.csv")
    daily = outlook.groupby(["route", "date"], as_index=False).p50.sum().merge(cal[["date", "kind"]], on="date")
    workdays = daily[(daily.route == 17) & daily.date.str.startswith("2026-03") & (daily.kind == "workday")]

    assert workdays.p50.nunique() == len(workdays)
    assert workdays.p50.max() / workdays.p50.min() - 1 > 0.02


def test_smooth_level_keeps_month_sums_without_a_step_at_the_border():
    from outlook_factors import smooth_daily

    dates = pd.Series(pd.date_range("2026-01-01", "2026-03-31").strftime("%Y-%m-%d"))
    month = dates.str.slice(0, 7)
    totals = month.map({"2026-01": 3100.0, "2026-02": 5600.0, "2026-03": 3100.0}).to_numpy()

    daily = smooth_daily(dates, np.ones(len(dates)), totals)

    sums = pd.Series(daily).groupby(month).sum()
    np.testing.assert_allclose(sums.to_numpy(), [3100, 5600, 3100], rtol=1e-9)
    steps = np.abs(np.diff(daily))
    assert steps.max() < 10, "уровень меняется плавно, без ступеньки 100 -> 200 на границе месяцев"
