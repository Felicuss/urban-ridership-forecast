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

    fact = labels[labels.date <= "2025-10-31"].boardings.to_numpy()
    assert np.array_equal(actuals.sort_values(["route", "date", "hour"]).boardings.to_numpy(),
                          labels[labels.date <= "2025-10-31"].sort_values(["route", "date", "hour"]).boardings.to_numpy())
    assert actuals.boardings.sum() == fact.sum()
    check(cal, actuals, outlook, year)
    assert cal[cal.date == "2026-01-09"].day_off.item(), "перенос выходного 2026 из производственного календаря"
    assert cal[cal.date == "2025-11-01"].day_type.item() == "workday", "рабочая суббота 1 ноября"
