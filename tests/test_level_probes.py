"""Пробы уровня s65: суммы по скорам проб восстанавливаются, файлы проб совпадают с журналом.

Запуск: uv run pytest tests/test_level_probes.py
"""

import numpy as np
import pytest

from s65_level_probes import (OUT, TOTAL_VALUE, ceiling, decode, entry_mask, load_ledger, platform_score,
                              probe_prediction, rake, synthetic_run, text_sha256, total_mask)


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


def test_where_fact_exceeds_ceiling_decode_gives_sum_of_min(synthetic):
    """Если факт выше потолка, проба измеряет Σmin(y, H), а не Σy: это нижняя граница суммы."""
    g, y, _, _, _ = synthetic
    base = g.prediction.to_numpy()
    target = {"group": [17, "wd", 11]}
    pred, meta = probe_prediction(g, target, [])
    m = entry_mask(g, target)
    h = ceiling(base[m], *meta["ceiling"])
    y = y.copy()
    idx = np.flatnonzero(m)[:10]
    y[idx] = h[:10] + 500
    total = base.copy()
    total[total_mask(g)] = TOTAL_VALUE
    rows = [{"id": "p10", "kind": "total", "sum_h": int(TOTAL_VALUE * total_mask(g).sum()),
             "score": platform_score(y, total)},
            {"id": "p11", "kind": "probe", **meta, "score": platform_score(y, pred)}]

    T, measured = decode(rows, platform_score(y, base))

    got = measured[0]["y"]
    assert abs(got - np.minimum(y[m], h).sum()) < T * 1e-5
    assert y[m].sum() - got > 4000, "10 ячеек по 500 посадок выше потолка"


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
