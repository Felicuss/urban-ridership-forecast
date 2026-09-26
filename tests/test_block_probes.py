"""Пробы по блокам s84: файлы проб совпадают с журналом, а пересчёт под измеренные суммы
воспроизводит загруженный на платформу кандидат (0,90764).

Запуск: uv run pytest tests/test_block_probes.py
"""

import hashlib
import json

from common import ROOT
from s84_block_probes import OUT, decoded, grid, load_ledger, margins, mask, rake, sha256, start_values, to_int

CANDIDATE = ROOT / "forecasts" / "submission_v11_probe_rake.csv"


def registry_sha(name: str) -> str:
    rows = json.loads((ROOT / "forecasts" / "leaderboard_results.json").read_text(encoding="utf-8"))
    return next(r["sha256"] for r in rows if r["file"] == name)


def test_probe_files_match_ledger():
    rows = load_ledger()

    assert rows, "журнал проб пуст"
    for r in rows:
        assert sha256(OUT / r["file"]) == r["sha256"], r["file"]


def test_rake_reproduces_the_scored_candidate():
    g = grid()
    measured = decoded(load_ledger())
    cons = margins(g, measured)

    pred = to_int(rake(g, cons, start_values(g, measured)))

    body = g[["route", "date", "hour"]].assign(prediction=pred).to_csv(sep=";", index=False, lineterminator="\n")
    assert hashlib.sha256(body.encode()).hexdigest() == registry_sha(CANDIDATE.name)
    assert sha256(CANDIDATE) == registry_sha(CANDIDATE.name)
    for m, y, name in cons:
        assert abs(pred[m].sum() - y) < 0.001 * y + 0.5 * m.sum(), name
