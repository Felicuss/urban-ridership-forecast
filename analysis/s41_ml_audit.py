"""Independent, standard-library audit of the profile/seasonality baseline.

Run: python3 analysis/s41_ml_audit.py
Does not overwrite submissions or service artifacts. Uses archived calendars.
This is a diagnostic, not a replacement for the production forecasting pipeline.
The fixed amplitude 0.83 is inherited from the existing solution, not nested-tuned.
"""

import csv
import datetime as dt
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/analysis/tables"
YEARS = (2019, 2022, 2023, 2024)
ROUTES = (1, 5, 7, 11, 12, 17, 25, 26, 28, 50)
AMPLITUDE = 0.83
FOLDS = {
    "W": ("2025-01-31", "2025-03-31"),
    "C": ("2025-04-30", "2025-06-30"),
    "E": ("2025-06-30", "2025-08-31"),
    "A": ("2025-08-31", "2025-10-31"),
    "B": ("2025-09-30", "2025-10-31"),
}


def rows(path, delimiter=","):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=delimiter))


def dates(start, end):
    for offset in range((end - start).days + 1):
        yield start + dt.timedelta(days=offset)


def write(name, data):
    with (OUT / name).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(data[0]))
        w.writeheader()
        w.writerows(data)


def main():
    calendar = {}
    for year in (*YEARS, 2025):
        for r in rows(ROOT / f"external/production_calendar_{year}_isdayoff.csv"):
            d, code = dt.date.fromisoformat(r["date"]), int(r["isdayoff_code"])
            off = code in (1, 8)
            kind = ("workday" if not off else "saturday" if d.weekday() == 5
                    else "sunday" if d.weekday() == 6 else "holiday")
            holiday = code == 8 or (off and d.weekday() < 5)
            calendar[d] = (kind, holiday)
    labels = {}
    daily = defaultdict(int)
    for name in ("train", "test"):
        for r in rows(ROOT / f"dataset/labels/labels_day_{name}.csv", ";"):
            route, d, hour, value = (int(r["route"]), dt.date.fromisoformat(r["date"]),
                                     int(r["hour"]), int(r["boardings"]))
            key = route, d, hour
            assert key not in labels, key
            labels[key] = value
            daily[d] += value
    city = {(int(r["year"]), int(r["month"])): float(r["passengers"])
            for r in rows(ROOT / "external/datamos_62521_monthly_ridership.csv")
            if r["transport"] == "Трамвай"}

    def day_weights(origin, legacy=False):
        grouped = defaultdict(list)
        for d, value in daily.items():
            if legacy:
                allowed = (dt.date(2025, 2, 1) <= d <= dt.date(2025, 6, 1)
                           and not dt.date(2025, 3, 31) <= d <= dt.date(2025, 4, 30))
            else:
                allowed = d <= origin
            if allowed:
                grouped[calendar[d][0]].append(value)
        work = median(grouped["workday"])
        return {k: median(v) / work for k, v in grouped.items()}

    def levels(weights=None):
        denom = defaultdict(float)
        for d, (kind, _) in calendar.items():
            denom[d.year, d.month] += 1 if weights is None else weights[kind]
        return {key: value / denom[key] for key, value in city.items() if key in denom}

    raw = levels()
    legacy = levels(day_weights(None, legacy=True))

    def season(index, origin, month, logarithmic=False):
        ratios = [index[y, month] / index[y, origin.month] for y in YEARS]
        if logarithmic:
            return math.exp(AMPLITUDE * median([math.log(r) for r in ratios]))
        return 1 + AMPLITUDE * (median(ratios) - 1)

    metrics, route_metrics = [], []
    # Additional exact 61-day horizons. They overlap: descriptive, not independent tests.
    extra = {f"R{m:02}": (dt.date(2025, m + 1, 1) - dt.timedelta(days=1)).isoformat()
             for m in range(1, 9)}
    folds = [(k, dt.date.fromisoformat(a), dt.date.fromisoformat(b), "existing")
             for k, (a, b) in FOLDS.items()]
    folds += [(k, dt.date.fromisoformat(a), dt.date.fromisoformat(a) + dt.timedelta(days=61), "rolling61")
              for k, a in extra.items()]
    for fold, origin, end, group in folds:
        profiles = {}
        for weeks in (2, 4, 8):
            bucket = defaultdict(list)
            start = max(dt.date(2025, 1, 1), origin - dt.timedelta(days=7 * weeks - 1))
            for d in dates(start, origin):
                kind, holiday = calendar[d]
                if holiday:
                    continue
                for route in ROUTES:
                    for h in range(24):
                        bucket[route, kind, h].append(labels.get((route, d, h), 0))
            profiles[weeks] = {k: median(v) for k, v in bucket.items()}
        normalized = levels(day_weights(origin))
        errors, pred_sum = defaultdict(float), defaultdict(float)
        errors_route, mass_route = defaultdict(float), defaultdict(float)
        mass, second_mass = 0, 0
        second_errors = defaultdict(float)
        for d in dates(origin + dt.timedelta(days=1), end):
            kind, holiday = calendar[d]
            kind = "sunday" if kind == "holiday" else kind
            rule = 0.95 if holiday and d.weekday() < 5 else 1.0
            if kind == "workday" and d.weekday() == 5:
                rule *= 0.85
            raw_k = season(raw, origin, d.month)
            norm_k = season(normalized, origin, d.month)
            legacy_k = season(legacy, origin, d.month, logarithmic=True)
            for route in ROUTES:
                for h in range(24):
                    key = route, kind, h
                    p = {w: profiles[w].get(key, 0) * rule for w in profiles}
                    variants = {
                        "profile_2w": p[2],
                        "s30_raw_2w": p[2] * raw_k,
                        "s30_raw_4w": p[4] * raw_k,
                        "s30_raw_median_2_4_8w": median(p.values()) * raw_k,
                        "calendar_normalized_2w": p[2] * norm_k,
                        "artifact_backtest_formula": p[2] * legacy_k,
                    }
                    y = labels.get((route, d, h), 0)
                    mass += y
                    mass_route[route] += y
                    second = (d - origin).days > 31
                    second_mass += y if second else 0
                    for name, value in variants.items():
                        err = abs(y - value)
                        errors[name] += err
                        pred_sum[name] += value
                        errors_route[name, route] += err
                        second_errors[name] += err if second else 0
        for name in errors:
            metrics.append(dict(fold=fold, group=group, origin=origin, end=end,
                                days=(end-origin).days, variant=name,
                                wape_score=1-errors[name]/mass,
                                bias_pct=100*(pred_sum[name]/mass-1),
                                score_after_day31=1-second_errors[name]/second_mass if second_mass else ""))
            if group == "existing":
                for route in ROUTES:
                    route_metrics.append(dict(fold=fold, variant=name, route=route,
                                              target_sum=mass_route[route],
                                              absolute_error=errors_route[name, route],
                                              contribution_pp=100*errors_route[name, route]/mass))

    # Check the independent calendar/profile implementation against recorded results.
    expected = {r["fold"].split(":")[0]: float(r["wape_score"])
                for r in rows(OUT / "exp_weather_normalized.csv") if r["variant"] == "без погоды"}
    artifact_scores = json.loads((ROOT / "artifacts/backtest_metrics.json").read_text())["wape_score"]["hour"]
    for r in metrics:
        if r["group"] == "existing" and r["variant"] == "profile_2w":
            assert abs(r["wape_score"] - expected[r["fold"]]) < 1e-10, (r, expected[r["fold"]])
        if r["group"] == "existing" and r["variant"] == "artifact_backtest_formula":
            assert abs(r["wape_score"] - artifact_scores[r["fold"]]) < 0.000051
    write("audit_ml_backtest.csv", metrics)
    write("audit_ml_route_errors.csv", route_metrics)
    print("PASS: independent 2-week profiles reproduce all five recorded baseline scores")
    for group in ("existing", "rolling61"):
        print(group)
        for name in dict.fromkeys(r["variant"] for r in metrics):
            selected = [r for r in metrics if r["group"] == group and r["variant"] == name]
            print(name, round(mean(r["wape_score"] for r in selected), 6),
                  "min", round(min(r["wape_score"] for r in selected), 6))
    origin = dt.date(2025, 10, 31)
    norm = levels(day_weights(origin))
    print("Nov/Dec raw:", [round(season(raw, origin, m), 4) for m in (11, 12)])
    print("Nov/Dec calendar-normalized:", [round(season(norm, origin, m), 4) for m in (11, 12)])


if __name__ == "__main__":
    main()
