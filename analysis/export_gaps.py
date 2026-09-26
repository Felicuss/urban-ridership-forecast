"""Пропуски в факте 2025 года: когда маршрут почти не записан в данных, почему и сколько было бы посадок.

Организаторы на встрече 26.09.2026: если в данных есть большой период без маршрута, плюс - назвать причину,
большой плюс - восстановить значения по предыдущим периодам. Здесь это делается так.

- Пропуск - день маршрута, где посадок меньше половины нормы. Норма - медиана того же маршрута и типа дня
  (будни, суббота, воскресенье и праздник) за 8 предыдущих нормальных дней этого типа; сами пропуски в норму
  не входят. Первые дни года без трёх нормальных дней для сравнения не проверяются.
- Соседние дни пропуска одного маршрута с разрывом до 6 дней склеиваются в период: так выходные подряд
  становятся одним закрытием.
- Причина - событие из external/events_2025.csv, которое накрывает маршрут, даты и тип дня, со ссылкой на пост
  Дептранса. Нет события - причина не найдена, так и пишем.
- Восстановление по часам - медиана тех же часов в 4 предыдущих нормальных днях того же типа.

Факт в сервисе остаётся фактом, восстановленные значения показываются рядом и в прогноз не подмешиваются.
Запуск - в составе s40_export_artifacts.py; проверка - tests/test_artifacts.py.
"""

import numpy as np
import pandas as pd

from common import ROOT
from typography import for_people

EVENTS = ROOT / "external" / "events_2025.csv"
THRESHOLD = 0.5
BASELINE_DAYS = 8
MIN_BASELINE = 3
RESTORE_DAYS = 4
MERGE_GAP_DAYS = 6
# маршрут 5 запущен 16.12.2025, в факте января-октября его нет вовсе: это не пропуск
SKIP_ROUTES = (5,)
KIND_LABEL = {"workday": "будни", "saturday": "субботы", "sunday": "воскресенья и праздники"}
EVENT_DAYS = {"all": None, "weekends": ("saturday", "sunday"), "workdays": ("workday",)}


def _flag(daily: pd.DataFrame) -> pd.DataFrame:
    """Норма и признак пропуска для каждого дня маршрута, по порядку дат внутри маршрута и типа дня."""
    rows = []
    for (route, kind), g in daily.groupby(["route", "kind"]):
        normal: list[float] = []
        for r in g.sort_values("date").itertuples():
            base = normal[-BASELINE_DAYS:]
            expected = float(np.median(base)) if len(base) >= MIN_BASELINE else np.nan
            gap = bool(expected > 0 and r.boardings < THRESHOLD * expected)
            rows.append({"route": route, "date": r.date, "kind": kind, "boardings": r.boardings,
                         "expected": expected, "gap": gap})
            if not gap:
                normal.append(float(r.boardings))
    return pd.DataFrame(rows)


def _periods(flags: pd.DataFrame) -> list[pd.DataFrame]:
    gaps = flags[flags.gap].sort_values(["route", "date"])
    out = []
    for _, g in gaps.groupby("route"):
        start = 0
        dates = g.date.to_list()
        for i in range(1, len(dates) + 1):
            if i == len(dates) or (dates[i] - dates[i - 1]).days > MERGE_GAP_DAYS + 1:
                out.append(g.iloc[start:i])
                start = i
    return out


def _reason(route: int, days: pd.DataFrame, events: pd.DataFrame) -> dict:
    """Событие, которое накрывает больше всего дней пропуска; при равенстве конкретное событие важнее сбоя данных."""
    best, best_key = None, (0, 0)
    for e in events.itertuples():
        routes = str(e.routes)
        if routes != "all" and str(route) not in routes.split(";"):
            continue
        kinds = EVENT_DAYS.get(str(e.days))
        inside = days[(days.date >= pd.Timestamp(e.start)) & (days.date <= pd.Timestamp(e.end))]
        if kinds is not None:
            inside = inside[inside.kind.isin(kinds)]
        key = (len(inside), 0 if e.type == "data_anomaly" else 1)
        if len(inside) and key > best_key:
            best, best_key = e, key
    if best is None:
        return {"reason": "причина не найдена: в новостях Дептранса и на mos.ru события нет", "type": "unknown",
                "source": ""}
    return {"reason": for_people(str(best.description)), "type": str(best.type), "source": str(best.source)}


def _restore(route: int, day: pd.Timestamp, kind: str, hourly: pd.DataFrame, flags: pd.DataFrame) -> list[int]:
    ok = flags[(flags.route == route) & (flags.kind == kind) & (flags.date < day) & ~flags.gap]
    ref = ok.sort_values("date").date.tail(RESTORE_DAYS)
    h = hourly[(hourly.route == route) & hourly.date.isin(ref)]
    by_hour = h.groupby("hour").boardings.median().reindex(range(24), fill_value=0)
    return [int(round(v)) for v in by_hour.to_numpy()]


def build_gaps(actuals: pd.DataFrame, calendar: pd.DataFrame) -> dict:
    hourly = actuals.assign(date=pd.to_datetime(actuals.date))
    hourly = hourly[~hourly.route.isin(SKIP_ROUTES)]
    cal = calendar.assign(date=pd.to_datetime(calendar.date))[["date", "kind"]]
    daily = hourly.groupby(["route", "date"]).boardings.sum().reset_index().merge(cal, on="date")
    flags = _flag(daily)
    events = pd.read_csv(EVENTS)
    periods, restored = [], {}
    for days in _periods(flags):
        route = int(days.route.iloc[0])
        restored_days = {}
        for d in days.itertuples():
            restored_days[d.date.strftime("%Y-%m-%d")] = _restore(route, d.date, d.kind, hourly, flags)
        restored.setdefault(str(route), {}).update(restored_days)
        kinds = sorted(set(days.kind), key=list(KIND_LABEL).index)
        periods.append({
            "route": route,
            "from": days.date.min().strftime("%Y-%m-%d"),
            "to": days.date.max().strftime("%Y-%m-%d"),
            "days": int(len(days)),
            "day_kinds": ", ".join(KIND_LABEL[k] for k in kinds),
            "fact": int(days.boardings.sum()),
            "expected": int(round(days.expected.sum())),
            "restored": int(sum(sum(v) for v in restored_days.values())),
            **_reason(route, days, events),
        })
    periods.sort(key=lambda p: (p["from"], p["route"]))
    return {
        "rule": f"день маршрута с посадками меньше {int(THRESHOLD * 100)} % нормы; норма - медиана {BASELINE_DAYS} "
                "предыдущих нормальных дней того же типа",
        "restore": f"по часам - медиана тех же часов в {RESTORE_DAYS} предыдущих нормальных днях того же типа",
        "periods": periods,
        "restored": restored,
    }
