"""Прогноз на 2025-11-01 … 2025-12-31: профиль октября × корректирующие коэффициенты.

Каждый коэффициент - отдельный внешний фактор с источником (см. docs/analysis/README.md),
все они собраны в Coefficients и сохраняются в forecasts/coefficients.json, чтобы
их можно было менять в интерфейсе и сразу пересчитывать прогноз.
Запуск: uv run python analysis/s10_forecast.py
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from common import (
    ACTIVE_ROUTES, DATASET, FORECAST_END, FORECAST_START, ROOT, ROUTES, TEST_END, TRAIN_START, load_labels,
)
from models import add_calendar, add_weather

OUT = ROOT / "forecasts"
SPRING_WINDOWS = [("2025-02-10", "2025-03-28"), ("2025-05-12", "2025-06-06")]  # без перекрытий у 7 и 50


@dataclass(frozen=True)
class Coefficients:
    profile_weeks: int = 4
    # сезонный уровень к октябрю (data.mos.ru 62521, поправка на календарь и Т1, наклон 0.83)
    level_nov: float = 1.015
    level_dec: float = 1.02
    # календарь (постановление № 1335, история праздников 2025)
    holiday_to_sunday: float = 0.95
    working_saturday: float = 0.85  # 01.11: рабочая сокращённая суббота перед 3 выходными
    last_workdays_dec: float = 0.85  # 29-30.12, экспертная оценка
    dec31_day: float = 0.90  # 31.12 днём относительно профиля праздника
    dec31_free_from_hour: int = 20  # с 20:00 бесплатный проезд, валидаций около 0
    # события сети (Дептранс)
    weekend_restore_date: str = "2025-11-15"  # выходные 7 и 50 снова по полной трассе
    t1_start: str = "2025-11-12"
    t1_route7: float = 0.95  # гипотеза: часть пассажиров общего участка уходит в Т1
    route5_on: bool = False
    route5_start: str = "2025-12-16 18:00"
    route5_workday: float = 5000.0  # около 160 тыс. поездок за первый месяц
    # погода (Open-Meteo, эффекты из s05/s09)
    weather: bool = True
    precip_day_coef: float = -0.0074
    hour_precip_coef: float = -0.035
    frost_coef: float = -0.0178


def load_history() -> pd.DataFrame:
    df = load_labels()
    return add_calendar(df, TRAIN_START, TEST_END)


def forecast_grid() -> pd.DataFrame:
    grid = pd.MultiIndex.from_product(
        [ROUTES, pd.date_range(FORECAST_START, FORECAST_END, freq="D"), range(24)], names=["route", "date", "hour"]
    ).to_frame(index=False)
    grid["ts"] = grid["date"] + pd.to_timedelta(grid["hour"], unit="h")
    grid = add_calendar(grid, FORECAST_START, FORECAST_END)
    return add_weather(grid)


def base_profile(hist: pd.DataFrame, grid: pd.DataFrame, weeks: int) -> np.ndarray:
    origin = hist.date.max()
    h = hist[(hist.date > origin - pd.Timedelta(days=7 * weeks)) & ~hist.is_holiday]
    prof = h.groupby(["route", "kind", "hour"])["boardings"].median()
    idx = pd.MultiIndex.from_arrays([grid.route, grid.kind, grid.hour])
    return np.nan_to_num(prof.reindex(idx).to_numpy(dtype=float))


def spring_weekend(hist: pd.DataFrame, route: int) -> tuple[dict, pd.DataFrame]:
    """Отношение выходных к будням и форма суток выходных маршрута весной, когда он ходил полностью."""
    mask = np.zeros(len(hist), dtype=bool)
    for a, b in SPRING_WINDOWS:
        mask |= hist.date.between(a, b).to_numpy()
    h = hist[mask & (hist.route == route) & ~hist.is_holiday]
    daily = h.groupby(["date", "kind"])["boardings"].sum().reset_index()
    med = daily.groupby("kind")["boardings"].median()
    ratios = {k: med[k] / med["workday"] for k in ("saturday", "sunday")}
    shape = h.groupby(["kind", "hour"])["boardings"].mean()
    shape = shape / shape.groupby(level=0).transform("sum")
    return ratios, shape


def apply_rules(hist: pd.DataFrame, grid: pd.DataFrame, base: np.ndarray, c: Coefficients) -> np.ndarray:
    pred = base.copy()
    g = grid
    month = g.date.dt.month.to_numpy()
    pred *= np.where(month == 11, c.level_nov, c.level_dec)

    # календарь
    weekday_holiday = (g.is_holiday & (g.dow < 5)).to_numpy()
    pred *= np.where(weekday_holiday, c.holiday_to_sunday, 1.0)
    working_sat = ((g.dow == 5) & (g.day_type == "workday")).to_numpy()
    pred *= np.where(working_sat, c.working_saturday, 1.0)
    last_days = g.date.isin(pd.to_datetime(["2025-12-29", "2025-12-30"])).to_numpy()
    pred *= np.where(last_days, c.last_workdays_dec, 1.0)

    # выходные 7 и 50 после восстановления трассы: уровень будней октября × весеннее отношение
    wd_daily = pd.Series(base, index=g.index)[g.kind == "workday"].groupby([g.route, g.date]).sum()
    wd_level = wd_daily.groupby(level=0).median()
    restore = pd.Timestamp(c.weekend_restore_date)
    for route in (7, 50):
        ratios, shape = spring_weekend(hist, route)
        sel = ((g.route == route) & g.kind.isin(["saturday", "sunday"]) & (g.date >= restore)).to_numpy()
        kinds = g.kind[sel].to_numpy()
        hours = g.hour[sel].to_numpy()
        day_total = wd_level[route] * np.array([ratios[k] for k in kinds])
        sh = shape.reindex(pd.MultiIndex.from_arrays([kinds, hours])).fillna(0).to_numpy()
        mult = np.where(month[sel] == 11, c.level_nov, c.level_dec)
        mult = mult * np.where(g.is_holiday[sel].to_numpy(), c.holiday_to_sunday, 1.0)
        pred[sel] = day_total * sh * mult

    # 31.12 после возврата выходных: для 7 и 50 это нерабочий день, и блок выше его перезаписал бы
    dec31 = (g.date == pd.Timestamp("2025-12-31")).to_numpy()
    pred *= np.where(dec31, c.dec31_day, 1.0)
    pred = np.where(dec31 & (g.hour >= c.dec31_free_from_hour).to_numpy(), 0.0, pred)

    # Т1 и маршрут 7
    t1 = ((g.route == 7) & (g.date >= pd.Timestamp(c.t1_start))).to_numpy()
    pred *= np.where(t1, c.t1_route7, 1.0)

    # маршрут 5: запуск 16.12 около 18:00, форма суток как у маршрута 50
    r5 = (g.route == 5).to_numpy()
    pred[r5] = 0.0
    if c.route5_on:
        start = pd.Timestamp(c.route5_start)
        prof50 = hist[(hist.route == 50) & (hist.date > hist.date.max() - pd.Timedelta(days=28))]
        sh = prof50.groupby(["kind", "hour"])["boardings"].mean()
        sh = sh / sh.xs("workday").sum()
        sel = r5 & (g.ts >= start).to_numpy()
        kinds = np.full(sel.sum(), "workday")  # форма будня: выходные 50 в октябре около нуля
        dayk = g.kind[sel].to_numpy()
        ratio = np.select([dayk == "saturday", dayk == "sunday"], [0.6, 0.5], 1.0)
        base5 = sh.reindex(pd.MultiIndex.from_arrays([kinds, g.hour[sel].to_numpy()])).to_numpy()
        pred[sel] = c.route5_workday * base5 * ratio
        pred = np.where(r5 & dec31 & (g.hour >= c.dec31_free_from_hour).to_numpy(), 0.0, pred)

    # погода (фактическая за ноябрь-декабрь 2025, Open-Meteo)
    if c.weather:
        adj = (c.precip_day_coef * g.precip_day.fillna(0) + c.hour_precip_coef * g.precipitation.fillna(0).clip(0, 3)
               + c.frost_coef * np.clip(-10 - g.temp_day.fillna(0), 0, None))
        pred *= np.exp(adj.to_numpy())
    return np.clip(pred, 0, None)


FM_CACHE = ROOT / "data" / "fm_forecast_novdec.parquet"


def fm_forecasts(hist: pd.DataFrame, grid: pd.DataFrame) -> pd.DataFrame:
    """Chronos-2, t0-beta и TimesFM 3.0 с календарными ковариатами от origin 31.10 на весь горизонт."""
    if FM_CACHE.exists():
        return pd.read_parquet(FM_CACHE)
    from s07_foundation_models import run_chronos, run_t0, run_timesfm

    full = pd.concat([hist, grid.assign(boardings=np.nan)], ignore_index=True)
    full["is_day_off"] = full["is_day_off"].astype(bool)
    origin, end = hist.date.max(), grid.date.max()
    parts = []
    for name, fn in (("chronos2", run_chronos), ("t0", run_t0), ("timesfm3", run_timesfm)):
        p = fn(full, origin, end, True).assign(model=name)
        parts.append(p)
    out = pd.concat(parts, ignore_index=True)
    out["pred"] = out["pred"].clip(lower=0)
    out.to_parquet(FM_CACHE)
    return out


DAILY_CACHE = ROOT / "data" / "fm_daily_novdec.parquet"


def daily_fm_forecasts(hist: pd.DataFrame, grid: pd.DataFrame) -> pd.DataFrame:
    """Chronos-2 и t0-beta на дневных суммах маршрута (горизонт 61 шаг), см. s17."""
    if DAILY_CACHE.exists():
        return pd.read_parquet(DAILY_CACHE)
    from s17_daily_fm import chronos, daily_frame, t0

    full = pd.concat([hist, grid.assign(boardings=np.nan)], ignore_index=True)
    d = daily_frame(full)
    origin, end = hist.date.max(), grid.date.max()
    dates = pd.date_range(origin + pd.Timedelta(days=1), end)
    parts = []
    for name, fn in (("daily_chronos2", chronos), ("daily_t0", t0)):
        pred = np.clip(fn(d, origin, end), 0, None)
        for i, route in enumerate(ACTIVE_ROUTES):
            parts.append(pd.DataFrame({"route": route, "date": dates, "model": name, "pred": pred[i]}))
    out = pd.concat(parts, ignore_index=True)
    out.to_parquet(DAILY_CACHE)
    return out


@dataclass(frozen=True)
class Mix:
    """Из чего собрана база прогноза до правил событий.

    profile: none - без профиля; plain - профиль 2 нед, все участники с равным весом (как в
    бэктесте s11); external_level - профиль 2 нед × уровень ноября/декабря из городской
    статистики, и он весит столько же, сколько среднее всех FM (смесь двух оценок уровня).
    members: почасовые FM (chronos2, t0, timesfm3) и дневные (daily_chronos2, daily_t0),
    дневные раскладываются по часам долями профиля.
    """

    profile: str = "plain"
    members: tuple[str, ...] = ()


def ensemble_base(hist: pd.DataFrame, grid: pd.DataFrame, mix: Mix, c: Coefficients) -> np.ndarray:
    prof = base_profile(hist, grid, weeks=2)
    fm_parts = []
    hourly = [m for m in mix.members if not m.startswith("daily_")]
    daily = [m for m in mix.members if m.startswith("daily_")]
    if hourly:
        fm = fm_forecasts(hist, grid).pivot_table(index=["route", "ts"], columns="model", values="pred")
        fm = fm.reindex(pd.MultiIndex.from_arrays([grid.route, grid.ts])).fillna(0)
        fm_parts += [fm[m].to_numpy() for m in hourly]
    if daily:
        day_sum = pd.Series(prof).groupby([grid.route.to_numpy(), grid.date.to_numpy()]).transform("sum").to_numpy()
        share = np.where(day_sum > 0, prof / np.where(day_sum > 0, day_sum, 1), 0)
        dfc = daily_fm_forecasts(hist, grid).pivot_table(index=["route", "date"], columns="model", values="pred")
        dfc = dfc.reindex(pd.MultiIndex.from_arrays([grid.route, grid.date])).fillna(0)
        fm_parts += [share * dfc[m].to_numpy() for m in daily]
    parts = list(fm_parts)
    if mix.profile != "none":
        p = prof
        if mix.profile == "external_level":
            p = prof * np.where(grid.date.dt.month.to_numpy() == 11, c.level_nov, c.level_dec)
        if mix.profile == "external_level" and fm_parts:
            parts = [p, np.mean(fm_parts, axis=0)]
        else:
            parts = [p, *fm_parts]
    return np.mean(parts, axis=0)


def make_forecast(c: Coefficients, mix: Mix | None = None) -> pd.DataFrame:
    hist = load_history()
    grid = forecast_grid()
    if mix is None:
        base = base_profile(hist, grid, c.profile_weeks)
        pred = apply_rules(hist, grid, base, c)
    else:
        base = ensemble_base(hist, grid, mix, c)
        # plain: внешний уровень умножается на весь ансамбль, как в раунде 1;
        # none и external_level: уровень уже внутри базы (у FM свой, у профиля внешний)
        rules = c if mix.profile == "plain" else dataclasses.replace(c, level_nov=1.0, level_dec=1.0)
        pred = apply_rules(hist, grid, base, rules)
    return grid.assign(base=base, prediction=pred)


def to_submission(fc: pd.DataFrame, path) -> pd.DataFrame:
    template = pd.read_csv(DATASET / "test_submission.csv", sep=";", parse_dates=["date"])
    sub = template.drop(columns="prediction").merge(fc[["route", "date", "hour", "prediction"]],
                                                    on=["route", "date", "hour"], how="left")
    if sub.prediction.isna().any() or len(sub) != 14640:
        raise ValueError("сетка сабмита не совпала с шаблоном")
    sub["prediction"] = sub["prediction"].round().astype(int)
    sub["date"] = sub["date"].dt.strftime("%Y-%m-%d")
    sub.to_csv(path, sep=";", index=False)
    return sub


NO_EXTERNAL = Coefficients(level_nov=1.0, level_dec=1.0, holiday_to_sunday=1.0, working_saturday=1.0,
                           last_workdays_dec=1.0, dec31_day=1.0, dec31_free_from_hour=24,
                           weekend_restore_date="2099-01-01", t1_route7=1.0, weather=False)
# В ансамблях foundation-модели сами видят праздники через ковариаты, а профиль берёт для них
# воскресенье, поэтому общий множитель праздника отключаем, чтобы не учесть его дважды.
ENSEMBLE_RULES = Coefficients(holiday_to_sunday=1.0)
DAILY_FM = ("daily_chronos2", "daily_t0")
VARIANTS = {
    "profile_only": (NO_EXTERNAL, None),
    "external_all": (Coefficients(), None),
    "external_all_route5": (Coefficients(route5_on=True), None),
    "ensemble_external": (ENSEMBLE_RULES, Mix("plain", ("chronos2", "t0"))),
    # раунд 2: дневные FM (s17) лучше почасовых на бэктесте и почти не уводят уровень
    "daily_fm_external": (ENSEMBLE_RULES, Mix("none", DAILY_FM)),
    "blend_external": (ENSEMBLE_RULES, Mix("external_level", DAILY_FM)),
    "blend_external_route5": (dataclasses.replace(ENSEMBLE_RULES, route5_on=True), Mix("external_level", DAILY_FM)),
    # итог по лидерборду 25.09.2026: маршрут 5 +0.41 п.п., возврат выходных 7/50 +1.16, календарные
    # правила +0.14, а погодная поправка -0.26 п.п. на эталоне, поэтому в финале погоды нет
    "final": (dataclasses.replace(ENSEMBLE_RULES, route5_on=True, weather=False), Mix("external_level", DAILY_FM)),
    # TimesFM 3.0: веса под некоммерческой лицензией, вариант только для сравнения
    "ensemble_timesfm_external_NONCOMMERCIAL": (ENSEMBLE_RULES, Mix("plain", ("t0", "timesfm3"))),
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    hist_oct = load_labels()
    oct_total = hist_oct[hist_oct.date.dt.month == 10].boardings.sum()
    for name, (coefs, mix) in VARIANTS.items():
        fc = make_forecast(coefs, mix)
        sub = to_submission(fc, OUT / f"submission_{name}.csv")
        meta = {"mix": dataclasses.asdict(mix) if mix else {"profile": f"{coefs.profile_weeks}w", "members": []},
                **dataclasses.asdict(coefs)}
        (OUT / f"coefficients_{name}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        tot = fc.groupby(fc.date.dt.month).prediction.sum()
        print(f"{name:22s} nov={tot[11]:,.0f} ({tot[11] / 30 / (oct_total / 31):.3f} к окт в сутки) "
              f"dec={tot[12]:,.0f} ({tot[12] / 31 / (oct_total / 31):.3f}) rows={len(sub)}")
        fc.to_parquet(ROOT / "data" / f"forecast_{name}.parquet")


if __name__ == "__main__":
    main()
