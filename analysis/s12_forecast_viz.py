"""Визуализация прогноза: тепловая карта загрузки по времени, дневная динамика, карта маршрутов.

Карта рисует трассы из OpenStreetMap (external/osm_tram_routes.geojson) и красит каждый
маршрут прогнозом посадок в выбранный час. Посадки в данных без привязки к остановке,
поэтому загрузка показана на уровне маршрута, а не остановки.
Запуск: uv run python analysis/s12_forecast_viz.py (после s10)
"""

import json

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import ACTIVE_ROUTES, DATA, MUTED, ROOT, SERIES, TEXT_SECONDARY, load_labels, savefig

MAP_TS = pd.Timestamp("2025-11-18 08:00")  # вторник, утренний пик


def load_fc() -> pd.DataFrame:
    # финальный вариант: смесь, правила событий и календаря, маршрут 5 с 16.12, без погодной поправки
    return pd.read_parquet(DATA / "forecast_final.parquet")


def heatmap(fc: pd.DataFrame) -> None:
    fig, axes = plt.subplots(3, 3, figsize=(16, 10), sharex=True, sharey=True)
    vmax = fc.groupby("route").prediction.quantile(0.99)
    dates = pd.date_range("2025-11-01", "2025-12-31")
    for ax, route in zip(axes.flat, ACTIVE_ROUTES, strict=True):
        m = fc[fc.route == route].pivot_table(index="hour", columns="date", values="prediction")
        im = ax.imshow(m.values, aspect="auto", cmap="Blues", vmin=0, vmax=vmax[route], origin="lower")
        ax.set_title(f"Маршрут {route}", loc="left")
        ax.grid(False)
        ticks = [i for i, d in enumerate(dates) if d.day in (1, 15)]
        ax.set_xticks(ticks, [dates[i].strftime("%d.%m") for i in ticks])
        ax.set_yticks(range(0, 24, 4))
        cb = fig.colorbar(im, ax=ax, shrink=0.85)
        cb.ax.tick_params(labelsize=7)
    for ax in axes[:, 0]:
        ax.set_ylabel("час")
    fig.suptitle(
        "Прогноз загрузки на ноябрь-декабрь 2025: посадок в час (цвет), по дням (ось X) и часам (ось Y). "
        "Светлые полосы - выходные и праздники",
        x=0.01, ha="left", fontsize=11,
    )
    fig.tight_layout()
    savefig(fig, "14_forecast_heatmap")


def daily_with_history(fc: pd.DataFrame) -> None:
    hist = load_labels()
    hist = hist[hist.route.isin(ACTIVE_ROUTES)]
    h = hist.groupby("date").boardings.sum() / 1000
    f = fc[fc.route.isin(ACTIVE_ROUTES)].groupby("date").prediction.sum() / 1000
    b = fc[fc.route.isin(ACTIVE_ROUTES)].groupby("date")["base"].sum() / 1000
    fig, ax = plt.subplots(figsize=(15, 4.8))
    ax.plot(h.index, h.values, color=SERIES[0], lw=1.2, label="факт (январь-октябрь)")
    ax.plot(b.index, b.values, color=MUTED, lw=1.2, label="база смеси до правил событий и погоды")
    ax.plot(f.index, f.values, color=SERIES[1], lw=1.6, label="прогноз с внешними факторами")
    ax.set_ylabel("тыс. посадок в сутки, 9 маршрутов")
    ax.set_ylim(bottom=0)
    notes = {"2025-11-04": "3-4.11\nпраздники", "2025-11-15": "15.11 выходные\n7 и 50 вернулись",
             "2025-12-31": "31.12"}
    for d, txt in notes.items():
        ts = pd.Timestamp(d)
        ax.annotate(txt, (ts, f.get(ts, 0)), xytext=(0, -38), textcoords="offset points", fontsize=7,
                    color=TEXT_SECONDARY, ha="center", arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.6})
    ax.legend(loc="lower left", ncols=3)
    ax.set_title("Суточные посадки: история и прогноз на ноябрь-декабрь 2025", loc="left")
    savefig(fig, "15_forecast_daily")


def route_map(fc: pd.DataFrame) -> None:
    geo = json.loads((ROOT / "external" / "osm_tram_routes.geojson").read_text(encoding="utf-8"))
    load = fc[fc.ts == MAP_TS].set_index("route").prediction
    norm = mpl.colors.Normalize(vmin=0, vmax=float(load.max()))
    cmap = mpl.colormaps["Blues"]
    fig, ax = plt.subplots(figsize=(11, 11))
    ax.set_facecolor("#f5f4f0")
    order = sorted(load.index, key=lambda r: load[r])  # сильнее загруженные рисуем поверх
    label_pos = {}
    for route in order:
        feats = [f for f in geo["features"] if f["properties"]["route"] == str(route)]
        val = float(load[route])
        color = cmap(0.25 + 0.75 * norm(val)) if val > 0 else MUTED
        lw = 1.2 + 4.0 * norm(val)
        for f in feats:
            if f["properties"]["kind"] != "track":
                continue
            xy = np.array(f["geometry"]["coordinates"])
            ax.plot(xy[:, 0], xy[:, 1], color=color, lw=lw, solid_capstyle="round", zorder=2 + norm(val))
        stops = np.array([f["geometry"]["coordinates"] for f in feats if f["properties"]["kind"] == "stop"])
        if len(stops):
            ax.scatter(stops[:, 0], stops[:, 1], s=4, color="white", edgecolor=color, lw=0.5, zorder=5)
            label_pos[route] = stops[len(stops) // 2]
    for route, (x, y) in label_pos.items():
        ax.text(x, y, f" {route}: {load[route]:,.0f}".replace(",", " "), fontsize=8, color="#0b0b0b", zorder=6,
                bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": "none", "alpha": 0.8})
    sm = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
    cb = fig.colorbar(sm, ax=ax, shrink=0.5, pad=0.01)
    cb.set_label("прогноз посадок за час на маршруте")
    ax.set_aspect(1 / np.cos(np.radians(55.75)))
    ax.margins(x=0.12, y=0.03)
    ax.set_xlabel("долгота")
    ax.set_ylabel("широта")
    ax.set_title(f"Трамвайные маршруты (OpenStreetMap) и прогноз загрузки на {MAP_TS:%d.%m.%Y %H:%M}", loc="left")
    ax.text(0.01, 0.01, "© OpenStreetMap contributors, ODbL. Маршрут 5 до 16.12 не работал.",
            transform=ax.transAxes, fontsize=7, color=TEXT_SECONDARY)
    savefig(fig, "16_map_forecast_peak")


def crowding(fc: pd.DataFrame) -> pd.DataFrame:
    """Посадки на вагон в час: прогноз на типичный будний день ноября / вагоны на линии в будни октября."""
    agg = pd.read_parquet(DATA / "route_hour_agg.parquet")
    agg["date"] = pd.to_datetime(agg["date"])
    octw = agg[(agg.date >= "2025-10-06") & (agg.date.dt.dayofweek < 5) & agg.route.isin(ACTIVE_ROUTES)]
    veh = octw.groupby(["route", "hour"])["vehicles"].median()
    nov = fc[(fc.date.between("2025-11-10", "2025-11-28")) & (fc.dow < 5) & fc.route.isin(ACTIVE_ROUTES)]
    load = nov.groupby(["route", "hour"])["prediction"].median()
    per_vehicle = (load / veh).unstack("hour").reindex(columns=range(5, 24))
    fig, ax = plt.subplots(figsize=(13, 4.6))
    im = ax.imshow(per_vehicle.values, cmap="Blues", aspect="auto")
    for i in range(per_vehicle.shape[0]):
        for j in range(per_vehicle.shape[1]):
            v = per_vehicle.values[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7,
                        color="white" if v > np.nanpercentile(per_vehicle.values, 70) else "#0b0b0b")
    ax.set_xticks(range(per_vehicle.shape[1]), per_vehicle.columns)
    ax.set_yticks(range(len(per_vehicle)), [f"м. {r}" for r in per_vehicle.index])
    ax.grid(False)
    ax.set_xlabel("час")
    fig.colorbar(im, ax=ax, shrink=0.8, label="посадок на вагон за час")
    ax.set_title("Индекс загрузки вагона: прогноз посадок в будни ноября на один вагон на линии (выпуск октября)",
                 loc="left")
    savefig(fig, "18_crowding_per_vehicle")
    return per_vehicle


def main() -> None:
    fc = load_fc()
    heatmap(fc)
    daily_with_history(fc)
    route_map(fc)
    pv = crowding(fc)
    top = pv.stack().sort_values(ascending=False).head(8)
    print("most loaded route-hours (boardings per vehicle):", top.round(0).to_dict())
    peak = fc[fc.route.isin(ACTIVE_ROUTES)].groupby(["route", "hour"]).prediction.mean().unstack().idxmax(axis=1)
    print("peak hour by route:", peak.to_dict())


if __name__ == "__main__":
    main()
