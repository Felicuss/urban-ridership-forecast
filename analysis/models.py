"""Модели прогноза для бэктеста. Каждая модель: (history, grid, origin) -> np.ndarray прогнозов.

history - почасовые посадки до origin включительно (route, date, hour, boardings),
grid    - ключи горизонта (route, date, hour) с календарём и погодой.
"""

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd

from calendar_ru import calendar_frame
from common import ROOT

WEATHER = ROOT / "external" / "weather_moscow_2025_hourly.csv"

# Правила для дней, которых нет в истории (подобраны по истории праздников, см. s02).
HOLIDAY_TO_SUNDAY = 0.95
WORKING_SATURDAY_TO_WORKDAY = 0.85


def kind_series(day_type: pd.Series) -> pd.Series:
    """Тип дня для профиля: праздник считаем воскресеньем."""
    return day_type.replace({"holiday": "sunday"})


def add_calendar(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    cal = calendar_frame(start, end)
    out = df.merge(cal[["date", "dow", "day_type", "is_holiday", "is_day_off"]], on="date", how="left")
    out["kind"] = kind_series(out["day_type"])
    return out


def add_weather(df: pd.DataFrame) -> pd.DataFrame:
    w = pd.read_csv(WEATHER, parse_dates=["ts"])
    w["date"] = w["ts"].dt.normalize()
    w["hour"] = w["ts"].dt.hour
    day = (
        w[w.hour.between(6, 22)]
        .groupby("date")
        .agg(precip_day=("precipitation", "sum"), snow_day=("snowfall", "sum"), temp_day=("temperature_2m", "mean"))
        .reset_index()
    )
    cols = ["date", "hour", "temperature_2m", "precipitation", "snowfall", "wind_speed_10m"]
    out = df.merge(w[cols], on=["date", "hour"], how="left").merge(day, on="date", how="left")
    return out


# ---------------------------------------------------------------- baselines


def baseline_blocks(history: pd.DataFrame, grid: pd.DataFrame, origin: pd.Timestamp) -> np.ndarray:
    """Как у организаторов: среднее по ненулевым строкам истории в блоках по 8 часов."""
    h = history[history.boardings > 0]
    means = h.groupby([h.route, h.hour // 8])["boardings"].mean()
    key = pd.MultiIndex.from_arrays([grid.route, grid.hour // 8])
    return means.reindex(key).fillna(0).to_numpy()


def seasonal_naive(history: pd.DataFrame, grid: pd.DataFrame, origin: pd.Timestamp) -> np.ndarray:
    """Последняя неделя истории: тот же тип дня (Пн-Пт по дню недели, праздник как воскресенье)."""
    last = history[history.date > origin - pd.Timedelta(days=7)]
    last = last.assign(key=np.where(last.kind == "workday", last.dow.astype(str), last.kind))
    val = last.groupby(["route", "key", "hour"])["boardings"].mean()
    g_key = np.where(grid.kind == "workday", grid.dow.astype(str), grid.kind)
    # праздник на месте рабочего дня недели в последней неделе - берём среднее рабочих
    fallback = last[last.kind == "workday"].groupby(["route", "hour"])["boardings"].mean()
    idx = pd.MultiIndex.from_arrays([grid.route, g_key, grid.hour])
    pred = val.reindex(idx).to_numpy()
    fb = fallback.reindex(pd.MultiIndex.from_arrays([grid.route, grid.hour])).to_numpy()
    return np.nan_to_num(np.where(np.isnan(pred), fb, pred))


# ---------------------------------------------------------------- профильная модель


@dataclass(frozen=True)
class ProfileConfig:
    weeks: int = 4
    stat: str = "median"  # median | mean
    by_dow: bool = False  # True: отдельный профиль для каждого дня Пн-Пт
    holiday_rules: bool = True
    weather: bool = False
    calendar: bool = True  # False: праздники считаем обычными днями недели
    precip_day_coef: float = -0.0074  # из s05: log-эффект на 1 мм осадков за 06-22
    hour_precip_coef: float = -0.035  # log-эффект на 1 мм в этот час, ограничен 3 мм


def _kind_by_dow(dow: pd.Series) -> np.ndarray:
    return np.where(dow == 5, "saturday", np.where(dow == 6, "sunday", "workday"))


def profile_forecast(
    history: pd.DataFrame, grid: pd.DataFrame, origin: pd.Timestamp, cfg: ProfileConfig
) -> np.ndarray:
    h = history[history.date > origin - pd.Timedelta(days=7 * cfg.weeks)].copy()
    if not cfg.calendar:
        h["kind"] = _kind_by_dow(h.dow)
        grid = grid.assign(kind=_kind_by_dow(grid.dow), is_holiday=False, day_type=_kind_by_dow(grid.dow))
    else:
        h = h[~h.is_holiday]  # праздники не портят профиль воскресенья
    if cfg.by_dow:
        h["key"] = np.where(h.kind == "workday", h.dow.astype(str), h.kind)
        g_key = np.where(grid.kind == "workday", grid.dow.astype(str), grid.kind)
    else:
        h["key"] = h.kind
        g_key = grid.kind.to_numpy()
    prof = h.groupby(["route", "key", "hour"])["boardings"].agg(cfg.stat)
    idx = pd.MultiIndex.from_arrays([grid.route, g_key, grid.hour])
    pred = prof.reindex(idx).to_numpy(dtype=float)
    if cfg.by_dow:  # рабочая суббота или редкий день недели без истории
        base = h[h.kind == "workday"].groupby(["route", "hour"])["boardings"].agg(cfg.stat)
        fb = base.reindex(pd.MultiIndex.from_arrays([grid.route, grid.hour])).to_numpy(dtype=float)
        pred = np.where(np.isnan(pred), fb, pred)
    pred = np.nan_to_num(pred)
    if cfg.holiday_rules:
        pred = pred * np.where(grid.is_holiday & (grid.dow < 5), HOLIDAY_TO_SUNDAY, 1.0)
        working_sat = (grid.dow == 5) & (grid.day_type == "workday")
        pred = pred * np.where(working_sat, WORKING_SATURDAY_TO_WORKDAY, 1.0)
    if cfg.weather:
        adj = (cfg.precip_day_coef * grid.precip_day.fillna(0)
               + cfg.hour_precip_coef * grid.precipitation.fillna(0).clip(0, 3))
        pred = pred * np.exp(adj.to_numpy())
    return pred


# ---------------------------------------------------------------- LightGBM с признаками от точки прогноза


def _origin_features(history: pd.DataFrame, origin: pd.Timestamp) -> pd.DataFrame:
    """Профили на дату origin: медиана за 2, 4 и 8 недель по маршрут × тип дня × час."""
    feats = []
    for weeks in (2, 4, 8):
        h = history[(history.date > origin - pd.Timedelta(days=7 * weeks)) & ~history.is_holiday]
        p = h.groupby(["route", "kind", "hour"])["boardings"].median().rename(f"prof_{weeks}w")
        feats.append(p)
    f = pd.concat(feats, axis=1).reset_index()
    lvl = history[(history.date > origin - pd.Timedelta(days=28)) & (history.kind == "workday")]
    lvl = lvl.groupby("route")["boardings"].sum() / max(lvl.date.nunique(), 1)
    f = f.merge(lvl.rename("route_level_4w").reset_index(), on="route", how="left")
    return f


def _frame_for_origin(history: pd.DataFrame, targets: pd.DataFrame, origin: pd.Timestamp) -> pd.DataFrame:
    f = _origin_features(history[history.date <= origin], origin)
    x = targets.merge(f, on=["route", "kind", "hour"], how="left")
    x["horizon_days"] = (x.date - origin).dt.days
    return x


LGB_FEATURES = [
    "route", "hour", "dow", "kind_code", "is_holiday", "horizon_days",
    "prof_2w", "prof_4w", "prof_8w", "route_level_4w",
    "temperature_2m", "precipitation", "snowfall", "precip_day", "snow_day", "temp_day",
]


@dataclass(frozen=True)
class LgbConfig:
    horizon: int = 61
    origin_step_days: int = 7
    first_origin: str = "2025-02-15"
    objective: str = "l1"
    use_weather: bool = True
    num_boost_round: int = 600


def lgb_forecast(history: pd.DataFrame, grid: pd.DataFrame, origin: pd.Timestamp, cfg: LgbConfig) -> np.ndarray:
    """Глобальная модель на разрезе (origin, target): цель - посадки, признаки - профили на origin,
    календарь и погода цели. Обучаем только на целях <= origin, т.е. без утечки."""
    kind_codes = {"workday": 0, "saturday": 1, "sunday": 2}
    rows = []
    o = pd.Timestamp(cfg.first_origin)
    while o < origin:
        tgt = history[(history.date > o) & (history.date <= min(o + pd.Timedelta(days=cfg.horizon), origin))]
        if len(tgt):
            rows.append(_frame_for_origin(history, tgt, o))
        o += pd.Timedelta(days=cfg.origin_step_days)
    train = pd.concat(rows, ignore_index=True)
    test = _frame_for_origin(history, grid, origin)
    feats = [c for c in LGB_FEATURES if cfg.use_weather or c not in {
        "temperature_2m", "precipitation", "snowfall", "precip_day", "snow_day", "temp_day"}]
    for df in (train, test):
        df["kind_code"] = df["kind"].map(kind_codes)
        df["is_holiday"] = df["is_holiday"].astype(int)
    params = {
        "objective": cfg.objective,
        "learning_rate": 0.03,
        "num_leaves": 63,
        "min_data_in_leaf": 50,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "verbose": -1,
        "seed": 42,
    }
    ds = lgb.Dataset(train[feats], train["boardings"], categorical_feature=["route"])
    model = lgb.train(params, ds, num_boost_round=cfg.num_boost_round)
    pred = model.predict(test[feats])
    return np.clip(pred, 0, None)


RATIO_FEATURES = [
    "route", "hour", "dow", "kind_code", "is_holiday", "horizon_days",
    "r2_4", "r8_4", "log_prof_4w",
    "temperature_2m", "precipitation", "snowfall", "precip_day", "snow_day", "temp_day",
]


def lgb_ratio_forecast(history: pd.DataFrame, grid: pd.DataFrame, origin: pd.Timestamp, cfg: LgbConfig) -> np.ndarray:
    """LightGBM предсказывает поправку к профилю 4 недель: y / (prof_4w + 1).
    Вес строки = prof_4w + 1, поэтому L1 по отношению = L1 по посадкам (метрика WAPE)."""
    kind_codes = {"workday": 0, "saturday": 1, "sunday": 2}
    rows = []
    o = pd.Timestamp(cfg.first_origin)
    while o < origin:
        tgt = history[(history.date > o) & (history.date <= min(o + pd.Timedelta(days=cfg.horizon), origin))]
        if len(tgt):
            rows.append(_frame_for_origin(history, tgt, o))
        o += pd.Timedelta(days=cfg.origin_step_days)
    train = pd.concat(rows, ignore_index=True)
    test = _frame_for_origin(history, grid, origin)
    for df in (train, test):
        df["kind_code"] = df["kind"].map(kind_codes)
        df["is_holiday"] = df["is_holiday"].astype(int)
        base = df["prof_4w"].fillna(0) + 1
        df["base"] = base
        df["r2_4"] = (df["prof_2w"].fillna(0) + 1) / base
        df["r8_4"] = (df["prof_8w"].fillna(0) + 1) / base
        df["log_prof_4w"] = np.log(base)
    train = train[train["base"] > 5]  # ночные часы с нулями дают шумные отношения
    feats = [c for c in RATIO_FEATURES if cfg.use_weather or c not in {
        "temperature_2m", "precipitation", "snowfall", "precip_day", "snow_day", "temp_day"}]
    params = {
        "objective": "l1",
        "learning_rate": 0.03,
        "num_leaves": 31,
        "min_data_in_leaf": 200,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "lambda_l2": 1.0,
        "verbose": -1,
        "seed": 42,
    }
    ds = lgb.Dataset(train[feats], train["boardings"] / train["base"], weight=train["base"],
                     categorical_feature=["route"])
    model = lgb.train(params, ds, num_boost_round=cfg.num_boost_round)
    ratio = model.predict(test[feats])
    pred = np.where(test["base"] > 5, ratio * test["base"], test["base"] - 1)
    return np.clip(pred, 0, None)


def ensemble(*fns):
    def run(history: pd.DataFrame, grid: pd.DataFrame, origin: pd.Timestamp) -> np.ndarray:
        return np.mean([fn(history, grid, origin) for fn in fns], axis=0)

    return run
