"""План по прошедшим дням для сервиса: прогноз, который диспетчер получил бы вечером накануне.

Каждый день 1 февраля - 31 октября 2025 прогнозируется профилем за 2 недели по данным до конца
предыдущего дня, как в s37. Часы вне работы маршрута нулевые, как в факте (export_timeline.actuals_frame),
иначе план и факт расходились бы на проверках оборудования. Январь не планируем: в первые недели года
профилю не на чем учиться из-за новогодних праздников.
"""

import numpy as np
import pandas as pd

from common import wape_score
from export_timeline import HOURS, service_hours
from models import ProfileConfig, profile_forecast
from s06_backtest import load_frame

PLAN_FROM, PLAN_TO = "2025-02-01", "2025-10-31"
PROFILE = ProfileConfig(weeks=2)


def plan_frame() -> pd.DataFrame:
    """route, date, hour, plan для каждой ячейки дней плана."""
    full = load_frame()
    days = []
    for day in pd.date_range(PLAN_FROM, PLAN_TO):
        grid = full[full.date == day].reset_index(drop=True)
        base = profile_forecast(full[full.date < day], grid.drop(columns="boardings"), day - pd.Timedelta(days=1), PROFILE)
        days.append(pd.DataFrame({"route": grid.route, "date": day.strftime("%Y-%m-%d"), "hour": grid.hour,
                                  "plan": np.asarray(base, dtype=float)}))
    plan = pd.concat(days, ignore_index=True)
    hours = service_hours()
    off = np.array([h not in hours.get(r, set(range(HOURS))) for r, h in zip(plan.route, plan.hour)])
    return plan.assign(plan=np.where(off, 0.0, plan.plan).round(1))


def plan_quality(plan: pd.DataFrame, actuals: pd.DataFrame) -> dict:
    """Точность плана против факта сервиса за те же дни: по часам и по суткам маршрута."""
    m = plan.merge(actuals, on=["route", "date", "hour"], validate="one_to_one")
    daily = m.groupby(["route", "date"])[["plan", "boardings"]].sum()
    return {"from": PLAN_FROM, "to": PLAN_TO, "method": "профиль за 2 недели по данным до конца предыдущего дня",
            "wape_score_hour": round(wape_score(m.boardings, m.plan), 4),
            "wape_score_day": round(wape_score(daily.boardings, daily.plan), 4)}


def check(plan: pd.DataFrame, routes: list[int]) -> None:
    days = pd.date_range(PLAN_FROM, PLAN_TO).size
    if len(plan) != len(routes) * days * HOURS or plan.duplicated(["route", "date", "hour"]).any():
        raise ValueError(f"план: {len(plan)} строк вместо {len(routes) * days * HOURS}")
    if plan.plan.isna().any() or (plan.plan < 0).any():
        raise ValueError("план: пропуски или отрицательные значения")
