"""Пробы уровня s65: суммы по скорам проб восстанавливаются, файлы проб совпадают с журналом.

Запуск: uv run pytest tests/test_level_probes.py
"""

import pytest

from s65_level_probes import OUT, decode, entry_mask, load_ledger, rake, synthetic_run, text_sha256


@pytest.fixture(scope="module")
def synthetic():
    g, y, rows, base_score = synthetic_run()
    T, measured = decode(rows, base_score)
    return g, y, rows, T, measured


def test_every_probe_scores_above_zero(synthetic):
    _, _, rows, _, _ = synthetic

    assert all(r["score"] > 0 for r in rows), "скор 0 ничего не сообщает о сумме"


def test_sums_are_recovered_from_scores(synthetic):
    g, y, _, T, measured = synthetic

    assert abs(T - y.sum()) < 500
    for e in measured:
        assert abs(e["y"] - y[entry_mask(g, e)].sum()) < 200, e["id"]


def test_rake_keeps_measured_sums(synthetic):
    g, _, _, T, measured = synthetic

    pred = rake(g, measured, T)

    for e in measured:
        assert abs(pred[entry_mask(g, e)].sum() - e["y"]) < 0.001 * e["y"] + 0.5 * e["cells"], e["id"]


def test_probe_files_match_ledger():
    rows = load_ledger()

    assert rows, "журнал проб пуст"
    for r in rows:
        assert text_sha256(OUT / r["file"]) == r["sha256"], r["file"]
