"""Предложение (вагоны на линии) против спроса и структура пассажиров по типам билетов.

Запуск: uv run python analysis/s04_supply_and_passengers.py
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from calendar_ru import calendar_frame
from common import (
    ACTIVE_ROUTES,
    DATA,
    RAW_PARQUET,
    SERIES,
    TABLES,
    TEST_END,
    TEXT_SECONDARY,
    TRAIN_START,
    connect,
    savefig,
)

P = f"'{RAW_PARQUET.as_posix()}'"
MONTH_RU = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт"]

# Порядок категорий фиксирован: цвет следует за категорией.
TICKET_CASE = """
    CASE
        WHEN good_type LIKE 'СКМО%' OR regexp_matches(good_type, 'СК[СУАО]') THEN 'учащиеся и студенты'
        WHEN good_type LIKE 'СКМ %' OR good_type LIKE 'СКМ с%' THEN 'льготные СКМ'
        WHEN good_type IN ('КОШЕЛЕК', 'ББК МГТ', 'СБП') OR good_type LIKE 'ВЕСБ%' THEN 'кошелёк и банк. карта'
        WHEN regexp_matches(good_type, 'дн|дней|сут|ММ\\+МГТ') THEN 'проездные'
        ELSE 'прочие льготы'
    END
"""
TICKET_ORDER = ["льготные СКМ", "кошелёк и банк. карта", "проездные", "учащиеся и студенты", "прочие льготы"]


def supply_vs_demand() -> pd.DataFrame:
    day = pd.read_parquet(DATA / "route_day_agg.parquet")
    day["date"] = pd.to_datetime(day["date"])
    cal = calendar_frame(TRAIN_START, TEST_END)
    day = day.merge(cal[["date", "day_type"]], on="date")
    work = day[(day.day_type == "workday") & day.route.isin(ACTIVE_ROUTES)].copy()
    work["per_vehicle"] = work["boardings"] / work["vehicles"]

    fig, axes = plt.subplots(3, 3, figsize=(15, 9), sharex=True, sharey=True)
    for ax, route in zip(axes.flat, ACTIVE_ROUTES, strict=True):
        g = work[work.route == route].set_index("date").sort_index()
        for col, color, lab in (("boardings", SERIES[0], "посадки"), ("vehicles", SERIES[1], "вагоны")):
            base = g[col].median()
            ax.plot(g.index, (g[col] / base * 100).rolling(5, center=True).median(), color=color, lw=1.6, label=lab)
        ax.axhline(100, color=TEXT_SECONDARY, lw=0.7)
        ax.set_title(f"Маршрут {route}", loc="left")
        ax.set_ylim(0, 180)
    axes.flat[0].legend(loc="lower left")
    fig.suptitle(
        "Рабочие дни: посадки и число вагонов с валидациями, индекс к медиане января-октября (=100), "
        "медиана по 5 рабочим дням",
        x=0.01, ha="left", fontsize=11,
    )
    fig.autofmt_xdate()
    fig.tight_layout()
    savefig(fig, "06_supply_vs_demand_index")

    # Корреляция изменений посадок и вагонов по неделям: насколько уровень объясняется выпуском.
    work["week"] = work["date"].dt.to_period("W")
    wk = work.groupby(["route", "week"])[["boardings", "vehicles"]].median()
    corr = (
        np.log(wk).groupby("route").diff().dropna().groupby("route").corr().xs("boardings", level=1)["vehicles"]
    )
    per_vehicle = work.groupby("route")["per_vehicle"].median()
    out = pd.DataFrame({"weekly_dlog_corr": corr, "boardings_per_vehicle_day": per_vehicle}).round(3)
    out.to_csv(TABLES / "supply_demand_corr.csv")
    return out


def weekend_route50() -> pd.DataFrame:
    day = pd.read_parquet(DATA / "route_day_agg.parquet")
    day["date"] = pd.to_datetime(day["date"])
    x = day[(day.route == 50) & (day.date >= "2025-08-01")].copy()
    x["dow"] = x["date"].dt.dayofweek
    return x[x.dow >= 5][["date", "dow", "boardings", "vehicles", "exits"]]


def ticket_mix(con) -> pd.DataFrame:
    mix = con.execute(f"""
        SELECT tran_ts::DATE AS date, {TICKET_CASE} AS cat, count(*) AS n
        FROM {P}
        WHERE validation_result = 1 AND tran_ts >= '2025-01-01' AND tran_ts < '2025-11-01'
        GROUP BY ALL
    """).df()
    mix["date"] = pd.to_datetime(mix["date"])
    days = calendar_frame(TRAIN_START, TEST_END)
    mix = mix.merge(days[["date", "day_type"]], on="date")
    mix = mix[mix.day_type == "workday"]
    mix["month"] = mix["date"].dt.month
    # Медиана по рабочим дням месяца: устойчива к дням с перекрытиями.
    per_day = mix.groupby(["month", "cat"])["n"].median().unstack("cat")[TICKET_ORDER]
    pv = mix.pivot_table(index="month", columns="cat", values="n", aggfunc="sum")[TICKET_ORDER]
    idx = per_day / per_day.loc[[9, 10]].mean() * 100

    fig, ax = plt.subplots(figsize=(10, 4.8))
    for i, cat in enumerate(TICKET_ORDER):
        ax.plot(idx.index, idx[cat], color=SERIES[i], lw=2, marker="o", ms=4, label=cat)
    ax.axhline(100, color=TEXT_SECONDARY, lw=0.7)
    ax.set_xticks(idx.index, MONTH_RU)
    ax.set_ylabel("индекс, сен-окт = 100")
    ax.legend(ncols=3, loc="lower left")
    ax.set_title(
        "Медиана посадок в рабочий день по группам билетов (все маршруты), индекс к сентябрю-октябрю",
        loc="left",
    )
    savefig(fig, "07_ticket_groups_monthly")

    hourly = con.execute(f"""
        SELECT hour(tran_ts) AS hour, {TICKET_CASE} AS cat, count(*) AS n
        FROM {P}
        WHERE validation_result = 1 AND tran_ts >= '2025-09-01' AND tran_ts < '2025-11-01'
              AND dayofweek(tran_ts) BETWEEN 1 AND 5
        GROUP BY ALL
    """).df().pivot_table(index="hour", columns="cat", values="n")[TICKET_ORDER]
    shares = hourly / hourly.sum() * 100
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for i, cat in enumerate(TICKET_ORDER[:4]):
        ax.plot(shares.index, shares[cat], color=SERIES[i], lw=2, label=cat)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlabel("час")
    ax.set_ylabel("% суточных посадок группы")
    ax.legend(loc="upper left")
    ax.set_title("Форма суток по группам билетов, будни сентября-октября", loc="left")
    savefig(fig, "08_ticket_groups_hourly")

    share = pv.div(pv.sum(axis=1), axis=0) * 100
    share.round(2).to_csv(TABLES / "ticket_group_share_by_month.csv")
    return share


def cards(con) -> pd.DataFrame:
    return con.execute(f"""
        WITH d AS (
            SELECT tran_ts::DATE AS date, count(*) AS trips, count(DISTINCT crd_hashcode) AS cards
            FROM {P} WHERE validation_result = 1 AND tran_ts >= '2025-09-01' AND tran_ts < '2025-11-01'
            GROUP BY 1
        )
        SELECT median(trips) AS trips_per_day, median(cards) AS cards_per_day,
               median(trips / cards) AS trips_per_card
        FROM d
    """).df()


def main() -> None:
    pd.set_option("display.width", 200)
    con = connect()
    print(supply_vs_demand())
    print("route 50 weekends since August:\n", weekend_route50().to_string())
    print("ticket group share by month, %:\n", ticket_mix(con).round(1))
    print(cards(con))


if __name__ == "__main__":
    main()
