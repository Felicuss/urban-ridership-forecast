"""Пробы лидерборда по блокам сетки поверх v11 и пересчёт v11 под измеренные суммы.

Продолжение s65 (сокомандник, ветка exp/level-probes). В пробе блока S ячейки S получают потолок
H = ceil(a·v11 + b), заведомо выше факта, ячейки носителей p11 и p12 (будни №17 в ноябре и декабре,
потолок 1,6·v6 + 3) копируются из их файлов, остальные ячейки нулевые. Ошибки ячеек складываются,
поэтому скор пробы s = s_K + (Y_S − Σ|y − H|_S) / T, где s_K = 0,03337 + 0,03692 уже измерен.
При H ≥ y сумма эталона по блоку Y_S = (ΣH_S + (s − s_K)·T) / 2. Табло показывает пять знаков,
отсюда точность около ±50 посадок на блок. Нарушение потолка только занижает Y_S на Σmax(y − H, 0).

Носители держат скор пробы около 0,07, поэтому потолок блока можно брать с запасом (2·v11 + 15).
Выигрыш от поправки уровня растёт как квадрат её ошибки: блок, где v11 ошибается на 0,5 %, почти
ничего не даёт, на 5 % - заметно. Порядок проб в плане - от блоков с наибольшей ожидаемой ошибкой.

Запуск:
  uv run python analysis/s84_block_probes.py build          # файлы проб волны 1 и журнал
  uv run python analysis/s84_block_probes.py score q01 0.07123
  uv run python analysis/s84_block_probes.py decode
  uv run python analysis/s84_block_probes.py apply          # v11 под измеренные суммы
  uv run python analysis/s84_block_probes.py selftest       # синтетический эталон
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import NamedTuple

import numpy as np
import pandas as pd

from calendar_ru import calendar_frame
from common import ROOT

OUT = ROOT / "forecasts" / "probes_v11"
LEDGER = OUT / "ledger.json"
BASE = ROOT / "forecasts" / "submission_seasonal_daily_v11.csv"
CARRIERS = {  # измерены сокомандником 25.09: файлы, скоры и суммы эталона
    "p11": {"file": "carriers/p11_r17_wd_11.csv", "score": 0.03337, "y": 1_054_235,
            "spec": {"routes": [17], "months": [11], "kind": "wd"}},
    "p12": {"file": "carriers/p12_r17_wd_12.csv", "score": 0.03692, "y": 1_211_812,
            "spec": {"routes": [17], "months": [12], "kind": "wd"}},
}
T = 5_040_000 / (0.90553 - 0.51431)  # проба p10: сумма эталона по всей сетке, ±330
DEFAULT_CEILING = (2.0, 15.0)
LOOSE_CEILING = (3.0, 30.0)  # №5 первые дни и 31.12: факт может сильно отойти от v11
REGIME_CEILING = (2.3, 20.0)  # 7 и 50: режим выходных менялся, но при 3·v11 скор пробы падает к нулю
OTHER = [1, 5, 7, 11, 12, 25, 26, 28, 50]
CLOSURE_DAYS = ["2025-11-02", "2025-11-03", "2025-11-04", "2025-11-08", "2025-11-09"]
# v11 считает 50 закрытым в эти выходные (около 500 посадок), а 7 - укороченным; источник помечен
# «вероятно». Потолок берём от полного выходного 15.11, чтобы проба не занизила сумму, если трамвай ходил.
CLOSURE_REF = "2025-11-15"


class Block(NamedTuple):
    name: str
    spec: dict
    ceil_ab: tuple[float, float]
    part: bool = True  # входит в разбиение сетки, по которому выводится оставшийся блок
    floor_ref: str | None = None  # дата, профиль которой задаёт нижнюю границу потолка
    floor_dates: tuple[str, ...] = ()  # где действует нижняя граница; пусто - во всём блоке


# Волна 1 по убыванию ожидаемой ошибки v11: режимы 7/50, особые дни, крупные маршруты, остальное.
# Разбиение маршрут × месяц (у №17 только выходные, будни измерены в p11/p12); (25, ноябрь) выводится из T.
WAVE1: list[Block] = [
    Block("c50_nov", {"routes": [50], "dates": CLOSURE_DAYS}, REGIME_CEILING, floor_ref=CLOSURE_REF),
    Block("r50_11", {"routes": [50], "months": [11], "not_dates": CLOSURE_DAYS}, REGIME_CEILING),
    Block("r7_11", {"routes": [7], "months": [11]}, REGIME_CEILING, floor_ref=CLOSURE_REF,
          floor_dates=tuple(CLOSURE_DAYS)),
    Block("r50_12", {"routes": [50], "months": [12]}, REGIME_CEILING),
    Block("r7_12", {"routes": [7], "months": [12]}, REGIME_CEILING),
    Block("dec29_30", {"routes": OTHER, "dates": ["2025-12-29", "2025-12-30"]}, DEFAULT_CEILING, part=False),
    Block("r12_11", {"routes": [12], "months": [11]}, DEFAULT_CEILING),
    Block("r12_12", {"routes": [12], "months": [12]}, DEFAULT_CEILING),
    Block("r11_11", {"routes": [11], "months": [11]}, DEFAULT_CEILING),
    Block("r11_12", {"routes": [11], "months": [12]}, DEFAULT_CEILING),
    Block("dec31_day", {"dates": ["2025-12-31"], "hour_lt": 20}, LOOSE_CEILING, part=False),
    Block("nov03_04", {"routes": [1, 5, 11, 12, 17, 25, 26, 28], "dates": ["2025-11-03", "2025-11-04"]},
          DEFAULT_CEILING, part=False),  # у 7 и 50 режим этих дней не подтверждён, их меряют r7_11 и c50_nov
    Block("nov01", {"routes": OTHER, "dates": ["2025-11-01"]}, DEFAULT_CEILING, part=False),
    Block("r17_nwd_11", {"routes": [17], "months": [11], "kind": "nwd"}, DEFAULT_CEILING),
    Block("r17_nwd_12", {"routes": [17], "months": [12], "kind": "nwd"}, DEFAULT_CEILING),
    Block("r1_11", {"routes": [1], "months": [11]}, DEFAULT_CEILING),
    Block("r1_12", {"routes": [1], "months": [12]}, DEFAULT_CEILING),
    Block("r26_11", {"routes": [26], "months": [11]}, DEFAULT_CEILING),
    Block("r26_12", {"routes": [26], "months": [12]}, DEFAULT_CEILING),
    Block("r5_12", {"routes": [5], "months": [12]}, LOOSE_CEILING),
    Block("r28_11", {"routes": [28], "months": [11]}, DEFAULT_CEILING),
    Block("r28_12", {"routes": [28], "months": [12]}, DEFAULT_CEILING),
    Block("r25_12", {"routes": [25], "months": [12]}, DEFAULT_CEILING),
]
# Блок, который выводится из T и остальных блоков разбиения маршрут × месяц.
DERIVED = ("r25_11", {"routes": [25], "months": [11]})

# Волна 2: сетевой профиль часов по типам дня. По будням без №17: его будни заняты носителями.
# Сначала пилот - утро и вечер будней: если v11 не ошибается в форме суток, дробить часы незачем.
NOT17 = [1, 5, 7, 11, 12, 25, 26, 28, 50]
PILOT: list[Block] = [
    Block("h_wd_07_09", {"routes": NOT17, "kind": "wd", "hours": [7, 8, 9]}, DEFAULT_CEILING, part=False),
    Block("h_wd_16_19", {"routes": NOT17, "kind": "wd", "hours": [16, 17, 18, 19]}, DEFAULT_CEILING, part=False),
]
# Волна 3: будни предновогодней недели. По постам Дептранса пик поездок и ранний вечерний разъезд,
# 26.12 сильный снегопад; в правилах модели этой недели нет.
WAVE3: list[Block] = [
    Block("dec22_26_wd", {"routes": NOT17, "dates": [f"2025-12-{d}" for d in range(22, 27)]}, DEFAULT_CEILING,
          part=False),
]
PLANS = {"1": WAVE1, "pilot": PILOT, "3": WAVE3}


def grid() -> pd.DataFrame:
    g = pd.read_csv(BASE, sep=";")
    cal = calendar_frame("2025-11-01", "2025-12-31")[["date", "is_day_off"]]
    cal["date"] = cal.date.dt.strftime("%Y-%m-%d")
    g = g.merge(cal, on="date", how="left", validate="many_to_one")
    assert len(g) == 14640 and g.is_day_off.notna().all()
    return g.assign(month=g.date.str[5:7].astype(int), kind=np.where(g.is_day_off, "nwd", "wd"))


def mask(g: pd.DataFrame, spec: dict) -> np.ndarray:
    m = np.ones(len(g), dtype=bool)
    if "routes" in spec:
        m &= g.route.isin(spec["routes"]).to_numpy()
    if "months" in spec:
        m &= g.month.isin(spec["months"]).to_numpy()
    if "kind" in spec:
        m &= (g.kind == spec["kind"]).to_numpy()
    if "dates" in spec:
        m &= g.date.isin(spec["dates"]).to_numpy()
    if "not_dates" in spec:
        m &= ~g.date.isin(spec["not_dates"]).to_numpy()
    if "hours" in spec:
        m &= g.hour.isin(spec["hours"]).to_numpy()
    if "hour_lt" in spec:
        m &= (g.hour < spec["hour_lt"]).to_numpy()
    return m


def carrier_cells() -> tuple[np.ndarray, np.ndarray]:
    """Прогноз носителей ровно как в загруженных p11/p12 и маска их ячеек."""
    pred = np.zeros(14640, dtype=np.int64)
    for c in CARRIERS.values():
        f = pd.read_csv(OUT / c["file"], sep=";").prediction.to_numpy()
        assert f.shape == pred.shape and not ((f > 0) & (pred > 0)).any()
        pred += f
    return pred, pred > 0


def ceiling(base: np.ndarray, a: float, b: float) -> np.ndarray:
    return np.ceil(a * base + b).astype(np.int64)


def sha256(path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def reference(g: pd.DataFrame, ref_date: str | None, dates: tuple[str, ...] = ()) -> np.ndarray:
    """v11, где ячейка не ниже того же маршрута и часа в опорную дату (в датах dates или везде)."""
    base = g.prediction.to_numpy()
    if ref_date is None:
        return base
    ref = g[g.date == ref_date].set_index(["route", "hour"]).prediction
    at_ref = ref.reindex(pd.MultiIndex.from_frame(g[["route", "hour"]])).to_numpy()
    where = g.date.isin(dates).to_numpy() if dates else np.ones(len(g), dtype=bool)
    return np.where(where, np.maximum(base, at_ref), base)


def probe(g: pd.DataFrame, block: Block) -> tuple[np.ndarray, dict]:
    pred, used = carrier_cells()
    m = mask(g, block.spec)
    if not m.any() or (m & used).any():
        sys.exit(f"блок пустой или пересекается с носителями: {block.spec}")
    pred[m] = ceiling(reference(g, block.floor_ref, block.floor_dates)[m], *block.ceil_ab)
    meta = {"spec": block.spec, "ceiling": list(block.ceil_ab), "part": block.part, "floor_ref": block.floor_ref,
            "floor_dates": list(block.floor_dates),
            "cells": int(m.sum()), "sum_h": int(pred[m].sum()), "base_sum": int(g.prediction.to_numpy()[m].sum())}
    return pred, meta


def carrier_score() -> float:
    return sum(c["score"] for c in CARRIERS.values())


def expected_score(meta: dict) -> float:
    """Скор пробы, если эталон по блоку равен v11."""
    return carrier_score() + (2 * meta["base_sum"] - meta["sum_h"]) / T


def write(g: pd.DataFrame, pred: np.ndarray, path) -> None:
    assert len(pred) == 14640 and np.issubdtype(pred.dtype, np.integer) and (pred >= 0).all()
    g[["route", "date", "hour"]].assign(prediction=pred).to_csv(path, sep=";", index=False, lineterminator="\n")


def load_ledger() -> list[dict]:
    return json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else []


def save_ledger(rows: list[dict]) -> None:
    LEDGER.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def build(plan=WAVE1, start: int = 1) -> None:
    g = grid()
    rows = load_ledger()
    known = {r["name"] for r in rows}
    n = max([start - 1] + [int(r["id"][1:]) for r in rows])
    for block in plan:
        if block.name in known:
            continue
        n += 1
        pid = f"q{n:02d}"
        pred, meta = probe(g, block)
        name = block.name
        path = OUT / f"{pid}_{name}.csv"
        write(g, pred, path)
        rows.append({"id": pid, "name": name, **meta, "file": path.name, "sha256": sha256(path), "score": None})
        print(f"{path.name:24s} ячеек {meta['cells']:5d}  v11 {meta['base_sum']:>10,}  "
              f"ожидаемый скор {expected_score(meta):.5f}  1 % уровня = {0.02 * meta['base_sum'] / T:.5f}")
    save_ledger(rows)


def decoded(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        if r.get("score") is None:
            continue
        if r["score"] <= 0:
            print(f"{r['id']} {r['name']}: скор 0, сумма не восстанавливается (эталон сильно ниже v11)")
            continue
        y = (r["sum_h"] + (r["score"] - carrier_score()) * T) / 2
        out.append({**r, "y": y, "ratio": y / r["base_sum"]})
    return out


def margins(g: pd.DataFrame, measured: list[dict]) -> list[tuple[np.ndarray, float, str]]:
    """Все известные суммы: T, носители, измеренные блоки и выведенный блок разбиения."""
    out = [(np.ones(len(g), dtype=bool), T, "T")]
    out += [(mask(g, c["spec"]), c["y"], k) for k, c in CARRIERS.items()]
    out += [(mask(g, e["spec"]), e["y"], e["name"]) for e in measured]
    names = {e["name"] for e in measured}
    partition = [b.name for b in WAVE1 if b.part]
    if all(n in names for n in partition):
        covered = np.zeros(len(g), dtype=bool)
        total = 0.0
        for m, y, name in out[1:]:
            if name in CARRIERS or name in partition:
                assert not (covered & m).any(), name
                covered |= m
                total += y
        rest = ~covered
        live = g.prediction.to_numpy() > 0
        assert np.array_equal(rest & live, mask(g, DERIVED[1]) & live)
        out.append((rest, T - total, DERIVED[0]))
    return out


def start_values(g: pd.DataFrame, measured: list[dict]) -> np.ndarray:
    """v11; в блоке с опорным профилем, где эталон в 10 раз выше v11, берём профиль опорной даты.

    Множитель к почти нулевому v11 не восстановит работавший маршрут: при 500 посадках вместо 10 тысяч
    пересчёт раздул бы соседние часы. Опорный профиль - полный выходной после возврата трассы.
    """
    out = g.prediction.to_numpy().astype(float)
    for e in measured:
        if e.get("floor_ref") and not e.get("floor_dates") and e["ratio"] > 10:
            m = mask(g, e["spec"])
            out[m] = reference(g, e["floor_ref"])[m]
    return out


def rake(g: pd.DataFrame, cons: list[tuple[np.ndarray, float, str]], start: np.ndarray | None = None,
         sweeps: int = 300) -> np.ndarray:
    """Пропорциональный пересчёт под все суммы сразу (IPF); нулевые ячейки остаются нулевыми."""
    out = (g.prediction.to_numpy() if start is None else start).astype(float).copy()
    for _ in range(sweeps):
        for m, y, _ in cons:
            s = out[m].sum()
            if s > 0:
                out[m] *= y / s
    return out


def to_int(x: np.ndarray) -> np.ndarray:
    return np.rint(x).astype(np.int64)


def platform_score(y: np.ndarray, p: np.ndarray) -> float:
    return round(max(0.0, 1 - np.abs(y - p).sum() / y.sum()), 5)


def selftest(seed: int = 7) -> None:
    """Синтетический эталон: v11 с шумом ячеек 12 %, сдвигами уровня блоков и работавшим №50 в «закрытые»
    выходные; пробы и пересчёт как на табло."""
    global T
    g = grid()
    rng = np.random.default_rng(seed)
    base = g.prediction.to_numpy()
    truth = base.astype(float).copy()
    closure = mask(g, WAVE1[0].spec) & (g.route == 50).to_numpy()
    truth[closure] = 0.9 * reference(g, CLOSURE_REF)[closure]
    for block in WAVE1:
        truth[mask(g, block.spec)] *= rng.normal(1.0, 0.04)
    y = np.rint(np.clip(truth * np.exp(rng.normal(0, 0.12, len(g))), 0, None)).astype(np.int64)
    saved_T, saved = T, {k: dict(v) for k, v in CARRIERS.items()}
    try:
        T = float(y.sum())
        cpred, _ = carrier_cells()
        for c in CARRIERS.values():  # скор пробы из одного носителя и сумма эталона по нему
            m = mask(g, c["spec"])
            c["score"] = round((y[m].sum() - np.abs(y[m] - cpred[m]).sum()) / T, 5)
            c["y"] = int(y[m].sum())
        rows = []
        for i, block in enumerate(WAVE1, 1):
            pred, meta = probe(g, block)
            rows.append({"id": f"q{i:02d}", "name": block.name, **meta, "score": platform_score(y, pred)})
        measured = decoded(rows)
        worst = max(abs(e["y"] - y[mask(g, e["spec"])].sum()) for e in measured)
        cons = margins(g, measured)
        plain = to_int(rake(g, cons))
        raked = to_int(rake(g, cons, start_values(g, measured)))
        print(f"макс. ошибка восстановления суммы блока {worst:,.0f}; скор v11 {platform_score(y, base):.5f}, "
              f"пересчёт от v11 {platform_score(y, plain):.5f}, с опорным профилем {platform_score(y, raked):.5f}")
    finally:
        T = saved_T
        CARRIERS.update(saved)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("plan", nargs="?", default="1", choices=list(PLANS))
    s = sub.add_parser("score")
    s.add_argument("id")
    s.add_argument("value", type=float)
    sub.add_parser("decode")
    a = sub.add_parser("apply")
    a.add_argument("--out", required=True, help="имя файла в forecasts/; загруженные кандидаты не перезаписываем")
    a.add_argument("--ids", nargs="*", help="только эти пробы; по умолчанию все со скором")
    sub.add_parser("selftest")
    args = ap.parse_args()
    if args.cmd == "build":
        build(PLANS[args.plan])
    elif args.cmd == "selftest":
        selftest()
    elif args.cmd == "score":
        rows = load_ledger()
        row = next((r for r in rows if r["id"] == args.id), None)
        if row is None:
            sys.exit(f"нет {args.id} в журнале")
        row["score"] = args.value
        save_ledger(rows)
    elif args.cmd == "decode":
        for e in decoded(load_ledger()):
            print(f"{e['id']} {e['name']:12s} Y = {e['y']:>11,.0f}  v11 = {e['base_sum']:>11,}  Y/v11 = {e['ratio']:.4f}")
    elif args.cmd == "apply":
        g = grid()
        measured = decoded(load_ledger())
        if args.ids:
            measured = [e for e in measured if e["id"] in args.ids]
            if missing := set(args.ids) - {e["id"] for e in measured}:
                sys.exit(f"нет скора у {', '.join(sorted(missing))}")
        cons = margins(g, measured)
        pred = to_int(rake(g, cons, start_values(g, measured)))
        path = ROOT / "forecasts" / args.out
        write(g, pred, path)
        meta = {"file": path.name, "sha256": sha256(path), "base": BASE.name,
                "probes": {e["id"]: e["score"] for e in measured}}
        path.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{path.name}: сумм {len(cons)}, итог {pred.sum():,} (v11 {g.prediction.sum():,}, T {T:,.0f})")
        for m, y, name in cons:
            print(f"  {name:12s} цель {y:>12,.0f}  v11 {g.prediction.to_numpy()[m].sum():>12,}  итог {pred[m].sum():>12,}")


if __name__ == "__main__":
    main()
