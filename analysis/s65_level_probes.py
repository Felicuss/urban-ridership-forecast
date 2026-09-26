"""Пробы уровня: сумма эталона по всей сетке и по группам ячеек в сравнении с v6.

Продолжение проб s19. В пробе множества M ячейки M получают прогноз H = ceil(a·v6 + b), остальные
ячейки — нули. Тогда WAPE-score пробы S = (2·Σmin(y, H) − ΣH) / T, где T — сумма эталона по всей
сетке, и расшифровка (ΣH + T·S) / 2 даёт Σmin(y, H) по M. Это сумма эталона Y_M, если потолок H
не ниже факта ни в одной ячейке, иначе чуть меньше: на историческом аналоге v6 для будней
маршрута 17 занижение до 184 посадок при потолке 1,6·v6 + 3 и до 19 при 1,8·v6 + 4
(docs/analysis/tables/level_probe_review_historical_ceiling.csv). Округление скора до пяти знаков
добавляет ещё ±T·10⁻⁵/2, около 65 посадок.

T даёт проба p10: v6 плюс 7000 в ноябрьских ячейках маршрута 5, где маршрута ещё нет и эталон
нулевой, так что скор падает ровно на ΣH / T. Чтобы скор пробы не опустился до нуля, в неё
добавляется уже измеренная группа-носитель с тем же потолком, что в её собственной пробе. Ошибки
на разных ячейках складываются, поэтому вклад носителя известен и вычитается.

Потолки проб считаются от v6, чтобы носители p11 и p12 оставались теми же файлами. rake()
пересчитывает прогноз (по умолчанию v11) пропорционально так, чтобы суммы по измеренным множествам
и по всей сетке совпали с пробами; маршрут 5 не меняется.

Журнал проб со скорами — forecasts/probes/level_probes.json, итоги —
docs/research/level_probes_2026-09-25.md.

Запуск:
  uv run python analysis/s65_level_probes.py probe-set dec29_30 --carrier p11
  uv run python analysis/s65_level_probes.py probe 12 wd 11 --carrier p11 --carrier p12
  uv run python analysis/s65_level_probes.py score p14 0.04123
  uv run python analysis/s65_level_probes.py decode
  uv run python analysis/s65_level_probes.py rake [--base forecasts/submission_seasonal_daily_v11.csv]
  uv run python analysis/s65_level_probes.py selftest
"""

import argparse
import hashlib
import json
import sys

import numpy as np
import pandas as pd

from common import ROOT

OUT = ROOT / "forecasts" / "probes"
LEDGER = OUT / "level_probes.json"
BASE = ROOT / "forecasts" / "submission_shape_facts_v6.csv"
BASE_SCORE = 0.90553
RAKE_BASE = ROOT / "forecasts" / "submission_seasonal_daily_v11.csv"
KEYS = ["route", "date", "hour"]
TOTAL_VALUE = 7000  # на 720 ноябрьских ячейках маршрута 5 скор падает примерно на 0,39
SOLO = (1.6, 3.0)  # потолок без носителя: скор пробы остаётся выше нуля
CARRIED = (1.8, 4.0)  # с носителем запас есть, а ячеек, где факт выше потолка, меньше

# Дни, где уровень задают экспертные правила s10, и выходные. Маршрут 5 везде исключён.
SETS = {
    "nov01": "1 ноября, рабочая суббота",
    "nov03_04": "3–4 ноября, праздники",
    "dec29_30": "29–30 декабря",
    "dec31_day": "31 декабря до 20:00",
    "nwd_nov": "выходные и праздники ноября",
    "nwd_dec": "выходные и праздники декабря",
    "r7_50_weekends": "выходные маршрутов 7 и 50 с 15 ноября",
}


def grid() -> pd.DataFrame:
    """v6 и тип дня из artifacts, соединённые по ключу маршрут × дата × час."""
    base = pd.read_csv(BASE, sep=";")
    kind = pd.read_csv(ROOT / "artifacts" / "forecast_components.csv", usecols=[*KEYS, "kind"])
    g = base.merge(kind, on=KEYS, how="left", validate="one_to_one")
    if len(g) != len(base) or g.kind.isna().any():
        sys.exit("календарь artifacts не покрывает сетку v6")
    return g.assign(part=np.where(g.kind == "workday", "wd", "nwd"),
                    month=g.date.str[5:7].astype(int)).drop(columns="kind")


def group_mask(g: pd.DataFrame, route: int, part: str, month: int) -> np.ndarray:
    return ((g.route == route) & (g.part == part) & (g.month == month)).to_numpy()


def set_mask(g: pd.DataFrame, name: str) -> np.ndarray:
    d = g.date
    m = {
        "nov01": d == "2025-11-01",
        "nov03_04": d.isin(["2025-11-03", "2025-11-04"]),
        "dec29_30": d.isin(["2025-12-29", "2025-12-30"]),
        "dec31_day": (d == "2025-12-31") & (g.hour < 20),
        "nwd_nov": (g.part == "nwd") & (g.month == 11),
        "nwd_dec": (g.part == "nwd") & (g.month == 12),
        "r7_50_weekends": g.route.isin([7, 50]) & (g.part == "nwd") & (d >= "2025-11-15"),
    }[name]
    return (m & (g.route != 5)).to_numpy()


def total_mask(g: pd.DataFrame) -> np.ndarray:
    return ((g.route == 5) & (g.month == 11)).to_numpy()


def entry_mask(g: pd.DataFrame, e: dict) -> np.ndarray:
    return group_mask(g, *e["group"]) if "group" in e else set_mask(g, e["set"])


def entry_label(e: dict) -> str:
    return f"маршрут {e['group'][0]} {e['group'][1]} {e['group'][2]}" if "group" in e else SETS[e["set"]]


def ceiling(base: np.ndarray, a: float, b: float) -> np.ndarray:
    return np.ceil(a * base + b).astype(np.int64)


def text_sha256(path) -> str:
    """sha256 с концами строк LF: на Windows git выписывает forecasts/ с CRLF."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_ledger() -> list[dict]:
    return json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else []


def save_ledger(rows: list[dict]) -> None:
    LEDGER.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def write_submission(g: pd.DataFrame, pred: np.ndarray, name: str):
    pred = np.asarray(pred)
    assert len(pred) == 14640 and np.issubdtype(pred.dtype, np.integer) and (pred >= 0).all()
    path = OUT / name
    g[["route", "date", "hour"]].assign(prediction=pred).to_csv(path, sep=";", index=False, lineterminator="\n")
    return path


def next_id(rows: list[dict]) -> str:
    return f"p{max([9] + [int(r['id'][1:]) for r in rows]) + 1:02d}"


def probe_prediction(g: pd.DataFrame, target: dict, carriers: list[dict]) -> tuple[np.ndarray, dict]:
    """target — {"group": [маршрут, wd|nwd, месяц]} или {"set": имя}; потолок носителя берётся из журнала."""
    base = g.prediction.to_numpy()
    pred = np.zeros(len(g), dtype=np.int64)
    used = np.zeros(len(g), dtype=bool)
    ids = [c["id"] for c in carriers]
    if len(set(ids)) != len(ids):
        sys.exit("носитель указан дважды")
    for c in carriers:
        if c["kind"] != "probe" or not c.get("score"):
            sys.exit(f"{c['id']} не годится в носители: нужна проба множества с измеренным скором выше нуля")
        m = entry_mask(g, c)
        if (m & used).any():
            sys.exit("носители пересекаются между собой")
        pred[m] = ceiling(base[m], *c["ceiling"])
        used |= m
    m = entry_mask(g, target)
    if not m.any():
        sys.exit("пустое множество")
    if (m & used).any():
        sys.exit("множество пересекается с носителем, нужен другой носитель")
    a, b = CARRIED if carriers else SOLO
    pred[m] = ceiling(base[m], a, b)
    meta = {**target, "ceiling": [a, b], "cells": int(m.sum()), "sum_h": int(pred[m].sum()),
            "base_sum": int(base[m].sum()), "carriers": [c["id"] for c in carriers]}
    return pred, meta


def decode(rows: list[dict], base_score: float = BASE_SCORE) -> tuple[float | None, list[dict]]:
    """T и Σmin(y, H) по каждому измеренному множеству: сумма эталона, если потолок не ниже факта."""
    total = next((r for r in rows if r["kind"] == "total" and r["score"] is not None), None)
    if total is None:
        return None, []
    T = total["sum_h"] / (base_score - total["score"])
    contrib, measured = {}, []
    for r in rows:
        if r["kind"] == "total" or r["score"] is None:
            continue
        if r["score"] <= 0:
            print(f"{r['id']}: скор 0, проба ничего не сообщает")
            continue
        s = r["score"] - sum(contrib[c] for c in r["carriers"])
        contrib[r["id"]] = s
        y = (r["sum_h"] + T * s) / 2
        measured.append({**r, "y": y, "ratio": y / r["base_sum"], "s": s})
    return T, measured


def rake(g: pd.DataFrame, measured: list[dict], T: float, base: np.ndarray | None = None,
         sweeps: int = 200) -> np.ndarray:
    """Прогноз base (по умолчанию v6 из g), пересчитанный пропорционально под суммы измеренных множеств
    и всей сетки; маршрут 5 фиксирован."""
    base = (g.prediction.to_numpy() if base is None else np.asarray(base)).astype(float)
    fixed = (g.route == 5).to_numpy()
    constraints = [(~fixed, T - base[fixed].sum())] + [(entry_mask(g, e) & ~fixed, e["y"]) for e in measured]
    out = base.copy()
    for _ in range(sweeps):
        for m, target in constraints:
            s = out[m].sum()
            if s > 0:
                out[m] *= target / s
    return np.rint(out).astype(np.int64)


# ---- проверка на синтетическом эталоне -------------------------------------------

def platform_score(y: np.ndarray, p: np.ndarray) -> float:
    return round(max(0.0, 1 - np.abs(y - p).sum() / y.sum()), 5)


def synthetic_run(seed: int = 3) -> tuple[pd.DataFrame, np.ndarray, list[dict], float]:
    """Эталон: v6 с шумом ячеек 12 % и ошибками правил в особые дни; пробы по тому же плану, что на табло."""
    g = grid()
    base = g.prediction.to_numpy()
    rng = np.random.default_rng(seed)
    shock = np.ones(len(g))
    for name, k in [("nov01", 1.12), ("nov03_04", 0.85), ("dec29_30", 0.80), ("dec31_day", 1.25),
                    ("nwd_nov", 1.03), ("nwd_dec", 0.97)]:
        shock[set_mask(g, name)] *= k
    y = np.rint(np.clip(base * 1.005 * shock * np.exp(rng.normal(0, 0.12, len(g))), 0, None)).astype(np.int64)
    y[total_mask(g)] = 0
    probe = base.copy()
    probe[total_mask(g)] = TOTAL_VALUE
    rows = [{"id": "p10", "kind": "total", "sum_h": int(TOTAL_VALUE * total_mask(g).sum()),
             "score": platform_score(y, probe)}]

    def add(target: dict, carriers: list[str]) -> None:
        by_id = {r["id"]: r for r in rows}
        pred, meta = probe_prediction(g, target, [by_id[c] for c in carriers])
        rows.append({"id": next_id(rows), "kind": "probe", **meta, "score": platform_score(y, pred)})

    add({"group": [17, "wd", 11]}, [])
    add({"group": [17, "wd", 12]}, [])
    for name, carriers in [("dec29_30", ["p11"]), ("nov01", ["p12"]), ("nov03_04", ["p11", "p12"]),
                           ("dec31_day", ["p11", "p12"]), ("nwd_nov", ["p11", "p12"]),
                           ("nwd_dec", ["p11", "p12"]), ("r7_50_weekends", ["p11", "p12"])]:
        add({"set": name}, carriers)
    return g, y, rows, platform_score(y, base)


def selftest() -> None:
    g, y, rows, base_score = synthetic_run()
    T, measured = decode(rows, base_score)
    for e in measured:
        print(f"{e['id']} {entry_label(e):40s} Y {e['y']:>11,.0f}  факт {y[entry_mask(g, e)].sum():>11,}  "
              f"скор пробы {e['score']:.5f}")
    print(f"T {T:,.0f}, факт {y.sum():,}; скор v6 {base_score:.5f}, после rake {platform_score(y, rake(g, measured, T)):.5f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    p = sub.add_parser("probe")
    p.add_argument("route", type=int)
    p.add_argument("part", choices=["wd", "nwd"])
    p.add_argument("month", type=int, choices=[11, 12])
    p.add_argument("--carrier", action="append", default=[])
    ps = sub.add_parser("probe-set")
    ps.add_argument("name", choices=list(SETS))
    ps.add_argument("--carrier", action="append", default=[])
    s = sub.add_parser("score")
    s.add_argument("id")
    s.add_argument("value", type=float)
    sub.add_parser("decode")
    rk = sub.add_parser("rake")
    rk.add_argument("--base", default=str(RAKE_BASE.relative_to(ROOT)), help="прогноз, который пересчитываем")
    args = ap.parse_args()

    if args.cmd == "selftest":
        selftest()
        return
    g = grid()
    rows = load_ledger()
    by_id = {r["id"]: r for r in rows}
    if args.cmd in ("probe", "probe-set"):
        if unknown := [c for c in args.carrier if c not in by_id]:
            sys.exit(f"нет в журнале: {', '.join(unknown)}")
        pid = next_id(rows)
        if args.cmd == "probe":
            target = {"group": [args.route, args.part, args.month]}
            name = f"{pid}_r{args.route}_{args.part}_{args.month}.csv"
        else:
            target, name = {"set": args.name}, f"{pid}_{args.name}.csv"
        pred, meta = probe_prediction(g, target, [by_id[c] for c in args.carrier])
        path = write_submission(g, pred, name)
        rows.append({"id": pid, "kind": "probe", **meta, "file": path.name, "sha256": text_sha256(path), "score": None})
        save_ledger(rows)
        T, measured = decode(rows)
        T = T or g.prediction.sum()
        expect = sum(e["s"] for e in measured if e["id"] in args.carrier) + (2 * meta["base_sum"] - meta["sum_h"]) / T
        print(f"{path}\n{entry_label(meta)}: ячеек {meta['cells']}, ΣH {meta['sum_h']:,}, v6 {meta['base_sum']:,}; "
              f"скор при эталоне, равном v6: {expect:.5f}; 1 % уровня сдвигает скор на "
              f"{0.02 * meta['base_sum'] / T:.5f}")
    elif args.cmd == "score":
        if args.id not in by_id:
            sys.exit(f"нет {args.id} в журнале")
        by_id[args.id]["score"] = args.value
        save_ledger(rows)
    elif args.cmd == "decode":
        T, measured = decode(rows)
        if T is None:
            sys.exit("нет скора пробы суммы")
        print(f"T = {T:,.0f}, в v6 {g.prediction.sum():,}, отношение {T / g.prediction.sum():.5f}")
        for e in measured:
            print(f"{e['id']} {entry_label(e):40s} Y = {e['y']:>12,.0f}, v6 = {e['base_sum']:>12,}, Y/v6 = {e['ratio']:.4f}")
    elif args.cmd == "rake":
        T, measured = decode(rows)
        if T is None:
            sys.exit("нет скора пробы суммы")
        src = pd.read_csv(ROOT / args.base, sep=";")
        if not src[KEYS].equals(g[KEYS]):
            sys.exit(f"ключи {args.base} не совпадают с сеткой v6")
        pred = rake(g, measured, T, src.prediction.to_numpy())
        path = write_submission(g, pred, f"level_probes_raked_{(ROOT / args.base).stem}.csv")
        print(f"{path}: множеств {len(measured)}, сумма {pred.sum():,} (исходно {src.prediction.sum():,}, T {T:,.0f})")


if __name__ == "__main__":
    main()
