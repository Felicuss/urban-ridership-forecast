"""Двухкомпонентная модель: прогноз = уровень дня маршрута × форма суток.

Уровень - медиана суточных посадок маршрута того же типа дня и того же режима (действующие события
сети из external/events_2025.csv) за последние недели до даты прогноза, умноженная на сезонный переход
трамвая Москвы (data.mos.ru, прошлые годы). Режим, которого ещё не было, - обычный уровень × множитель
по типу события. Форма - поровну доли часов того же типа дня за 8 недель с полураспадом 14 дней и сезонная
модель долей по типу дня, дню недели, годовой гармонике и погоде, как у v10. Каждый множитель
виден отдельно, поэтому такой прогноз сервис может разложить по шагам без непрозрачной поправки до v11.

Поправка уровня LightGBM (календарь, погода, горизонт, тренд) на фолдах ухудшала скор: 0.835 со всеми
признаками и 0.848 с календарём и погодой против 0.857 без неё. Отчёт: docs/research/level_shape_2026-09-27.md.

Проверка на фолдах цепочки v11 (s47: R04-R08 по 61 дню, B - октябрь): модель каждого фолда видит
только посадки до его начала. Скоры v11 на тех же фолдах - из docs/research/seasonal_daily_v11_2026-09-26.md.

Запуск: PYTHONUTF8=1 uv run python analysis/s85_level_shape.py [future]
"""

import json
import sys

import numpy as np
import pandas as pd

from calendar_ru import calendar_frame
from common import ROOT, ROUTES, TABLES, load_labels, wape_score

FOLDS = [("R04", "2025-04-30", 61), ("R05", "2025-05-31", 61), ("R06", "2025-06-30", 61),
         ("R07", "2025-07-31", 61), ("R08", "2025-08-31", 61), ("B", "2025-09-30", 31)]
V11 = {"R04": 0.859807, "R05": 0.859652, "R06": 0.861766, "R07": 0.840069, "R08": 0.863649, "B": 0.909753}
HISTORY_START = "2025-01-01"
LEVEL_DAYS = {"workday": 21, "saturday": 28, "sunday": 28}
SHAPE_DAYS = 56
SHAPE_HALF_LIFE = 14
CITY_YEARS = (2019, 2022, 2023, 2024)
# наши маршруты повторяют сезонные колебания городского трамвая с амплитудой 0.83, как в s10 и s30
AMPLITUDE = 0.83
# обычные дни этого типа старше месяца (маршрут долго был в другом режиме) уже не показывают уровень:
# тогда уровень выходных строится от свежих будней через отношение выходных к будням
STALE_DAYS = 35


def calendar() -> pd.DataFrame:
    cal = calendar_frame(HISTORY_START, "2025-12-31")
    # праздник в будний день ездит как воскресенье: для уровня и формы это один тип дня
    kind = cal.day_type.replace({"holiday": "sunday"})
    return cal.assign(kind=kind).set_index("date")


def city_season() -> pd.Series:
    """Поездки трамвая Москвы в сутки по месяцам, среднее отношение к январю по прошлым годам."""
    c = pd.read_csv(ROOT / "external/datamos_62521_monthly_ridership.csv")
    c = c[(c.transport == "Трамвай") & c.year.isin(CITY_YEARS)].pivot(index="year", columns="month", values="per_day")
    return AMPLITUDE * np.log(c.div(c[1], axis=0)).mean()


# Множитель события по его типу, как известно из объявления Дептранса: без измеренного эффекта, чтобы
# на фолдах не подглядывать в посадки внутри горизонта.
REGIME_PRIOR = {"full": 0.0, "short": 0.45, "merge": 1.1, "detour": 0.85}
REGIME_TYPES = {"closure", "merge", "detour"}
REGIME_LOOKBACK = 120


def network_events() -> list[dict]:
    """Режимы маршрутов из каталога событий: закрытия, укорочения, объединения, объезды."""
    e = pd.read_csv(ROOT / "external/events_2025.csv", parse_dates=["start", "end"])
    out = []
    for i, r in enumerate(e.itertuples()):
        # запись «режим продолжается» только уточняет даты уже действующего режима
        if r.type not in REGIME_TYPES or r.routes == "all" or "продолжается" in r.description:
            continue
        kind = ("merge" if r.type == "merge" else "detour" if r.type == "detour"
                else "full" if "не работал" in r.description else "short")
        out.append(dict(id=i, kind=kind, routes={int(x) for x in r.routes.split(";")}, start=r.start, end=r.end,
                        days=r.days))
    return out


def daily_weather() -> pd.DataFrame:
    """Погода дня для формы суток: средняя температура и дождь за 6-22 ч (Open-Meteo, разрешённые данные)."""
    w = pd.read_csv(ROOT / "external/weather_moscow_2025_hourly.csv", parse_dates=["ts"])
    w = w[(w.ts.dt.hour >= 6) & (w.ts.dt.hour <= 22)]
    day = w.groupby(w.ts.dt.normalize())
    return pd.DataFrame({"temp": day.temperature_2m.mean() / 20, "rain": day.precipitation.mean()})


# Сезонная модель долей часов, как у v10 (s80): робастная ридж-регрессия долей на тип дня, день недели,
# годовую гармонику, погоду и сезон × выходные, с поправкой на смещение последних 6 недель.
SHAPE_RIDGE = 20.0
SHAPE_RECENCY = 180
SHAPE_BIAS_DAYS = 42
SHAPE_ITERATIONS = 12
SHAPE_MODEL_WEIGHT = 0.5


def anomalies() -> set:
    a = pd.read_csv(ROOT / "docs/analysis/tables/anomalous_days.csv", parse_dates=["date"])
    return set(zip(a.route, a.date))


class Data:
    def __init__(self):
        labels = load_labels()
        self.hourly = labels.pivot_table(index=["route", "date"], columns="hour", values="boardings").sort_index()
        self.daily = self.hourly.sum(axis=1)
        self.cal = calendar()
        self.season = city_season()
        self.bad = anomalies()
        self.events = network_events()
        self._regime = {}
        self.dates = pd.date_range(HISTORY_START, "2025-12-31")
        self.weather = daily_weather().reindex(self.dates)

    def design(self) -> np.ndarray:
        kinds = self.cal.kind.reindex(self.dates).map({"workday": 0, "saturday": 1, "sunday": 2}).to_numpy()
        dow = self.cal.dow.reindex(self.dates).to_numpy()
        t = 2 * np.pi * (self.dates.dayofyear.to_numpy() - 1) / 365
        season = np.column_stack([np.sin(t), np.cos(t)])
        temp = self.weather.temp.to_numpy()
        return np.column_stack([np.eye(3)[kinds], np.eye(7)[dow][:, :6], season, temp, np.maximum(-temp, 0),
                                self.weather.rain.to_numpy(), season * (kinds != 0)[:, None]]), kinds

    def model_shapes(self, route: int, origin: pd.Timestamp) -> np.ndarray:
        """Доли часов на каждый день года по сезонной модели, обученной на днях маршрута до origin."""
        x, kinds = self.design()
        h = self.hourly.loc[route].reindex(self.dates).to_numpy()
        total = h.sum(axis=1)
        cutoff = self.dates.get_loc(origin)
        idx = np.arange(cutoff + 1)
        good = np.isfinite(total[idx]) & (total[idx] > 0.2 * np.nanmedian(total[idx]))
        good &= np.array([(route, self.dates[i]) not in self.bad for i in idx])
        ix = idx[good]
        y = h[ix] / total[ix, None] * 24
        xx = x[ix]
        importance = total[ix] / np.median(total[ix]) * np.exp((ix - cutoff) / SHAPE_RECENCY)
        reg = np.full(x.shape[1], SHAPE_RIDGE)
        reg[:3] = 0.001
        reg[3:9] = SHAPE_RIDGE * 2
        weights = np.broadcast_to(importance, (24, len(ix))).copy()
        for _ in range(SHAPE_ITERATIONS):
            lhs = np.einsum("ni,hn,nj->hij", xx, weights, xx) + np.diag(reg)[None]
            rhs = np.einsum("ni,hn,nh->hi", xx, weights, y)
            beta = np.linalg.solve(lhs, rhs[..., None])[..., 0]
            residual = y - np.einsum("ni,hi->nh", xx, beta)
            weights = importance[None] / np.maximum(np.abs(residual.T), 0.04)
        pred = np.einsum("ni,hi->nh", x, beta)
        fitted = np.einsum("ni,hi->nh", xx, beta)
        for k in range(3):
            local = (ix > cutoff - SHAPE_BIAS_DAYS) & (kinds[ix] == k)
            if local.sum() >= 3:
                pred[kinds == k] += 0.5 * np.median((y - fitted)[local], axis=0)
        pred = np.maximum(pred, 0.001)
        return pred / pred.sum(axis=1, keepdims=True)

    def regime(self, route: int, date: pd.Timestamp) -> frozenset:
        """Типы событий, которые действуют на маршрут в этот день с учётом типа дня: закрытие, укорочение,
        объединение, объезд. Два одинаковых по типу события - один режим."""
        key = (route, date)
        if key not in self._regime:
            kind = self.cal.kind[date]
            self._regime[key] = frozenset(
                e["kind"] for e in self.events
                if route in e["routes"] and e["start"] <= date <= e["end"]
                and (e["days"] == "all" or (e["days"] == "weekends") == (kind != "workday")))
        return self._regime[key]

    def regime_level(self, route: int, origin: pd.Timestamp, target: pd.Timestamp) -> tuple[float, int]:
        """Уровень дня в том же режиме, что и target: медиана недавних дней того же типа и с теми же событиями.
        Если режим ещё не встречался, - обычный уровень × множители событий. Второе значение - месяц истории."""
        kind = self.cal.kind[target]
        want = self.regime(route, target)
        days = self.recent(route, origin, kind, want)
        factor = 1.0
        if len(days) < 2:
            days = self.recent(route, origin, kind, frozenset())
            factor = float(np.prod([REGIME_PRIOR[k] for k in want]))
        if not days:
            return 0.0, origin.month
        if kind != "workday" and (origin - days[0]).days > STALE_DAYS:
            anchored = self.anchored(route, origin, days)
            if anchored is not None:
                return anchored[0] * factor, anchored[1]
        return self.median(route, days) * factor, days[len(days) // 2].month

    def recent(self, route: int, origin: pd.Timestamp, kind: str, regime: frozenset,
               before: pd.Timestamp | None = None) -> list[pd.Timestamp]:
        """Последние дни маршрута этого типа и режима, от свежих к старым."""
        count = max(2, LEVEL_DAYS[kind] // 7 * (5 if kind == "workday" else 1))
        days = []
        d = before or origin
        stop = max(origin - pd.Timedelta(days=REGIME_LOOKBACK), pd.Timestamp(HISTORY_START))
        while d >= stop and len(days) < count:
            if self.cal.kind[d] == kind and (route, d) not in self.bad and self.regime(route, d) == regime:
                days.append(d)
            d -= pd.Timedelta(days=1)
        return days

    def median(self, route: int, days: list[pd.Timestamp]) -> float:
        return float(self.daily.reindex([(route, d) for d in days]).fillna(0).median())

    def anchored(self, route: int, origin: pd.Timestamp, old: list[pd.Timestamp]) -> tuple[float, int] | None:
        """Свежий уровень обычных будней × отношение выходных к будням в том периоде, где были old."""
        now = self.recent(route, origin, "workday", frozenset())
        if len(now) < 2 or (origin - now[0]).days > STALE_DAYS:
            return None
        then = self.recent(route, origin, "workday", frozenset(), before=old[0] + pd.Timedelta(days=7))
        if len(then) < 2 or self.median(route, then) <= 0:
            return None
        ratio = self.median(route, old) / self.median(route, then)
        return self.median(route, now) * ratio, now[len(now) // 2].month

    def history(self, route: int, origin: pd.Timestamp, kind: str, days: int) -> pd.DataFrame:
        """Дни маршрута того же типа за days дней до origin включительно, без аномальных."""
        dates = pd.date_range(max(origin - pd.Timedelta(days=days - 1), pd.Timestamp(HISTORY_START)), origin)
        dates = [d for d in dates if self.cal.kind[d] == kind and (route, d) not in self.bad]
        return self.hourly.loc[route].reindex(dates).dropna()

    def level(self, route: int, origin: pd.Timestamp, kind: str) -> float:
        h = self.history(route, origin, kind, LEVEL_DAYS[kind])
        return float(h.sum(axis=1).median()) if len(h) else 0.0

    def shape(self, route: int, origin: pd.Timestamp, kind: str) -> np.ndarray:
        h = self.history(route, origin, kind, SHAPE_DAYS)
        totals = h.sum(axis=1)
        h = h[totals > 0]
        if h.empty:
            return np.full(24, 1 / 24)
        age = (origin - h.index).days.to_numpy()
        w = 0.5 ** (age / SHAPE_HALF_LIFE)
        shares = h.div(h.sum(axis=1), axis=0).to_numpy()
        return (shares * w[:, None]).sum(axis=0) / w.sum()


def frame(data: Data, origin: pd.Timestamp, days: int) -> pd.DataFrame:
    """Маршрут × день горизонта: обычный уровень, уровень в режиме и сезонные переходы к дню прогноза."""
    rows = []
    targets = pd.date_range(origin + pd.Timedelta(days=1), periods=days)
    for route in ROUTES:
        if route == 5:
            continue
        base = {k: data.level(route, origin, k) for k in LEVEL_DAYS}
        for t in targets:
            c = data.cal.loc[t]
            regime_level, regime_month = data.regime_level(route, origin, t)
            rows.append(dict(route=route, date=t, kind=c.kind, dow=c.dow, level=base[c.kind],
                             season=data.season[t.month] - data.season[origin.month],
                             regime_level=regime_level, regime_season=data.season[t.month] - data.season[regime_month]))
    return pd.DataFrame(rows)


def hourly(data: Data, fold: pd.DataFrame, origin: pd.Timestamp, totals: np.ndarray,
           model_weight: float = SHAPE_MODEL_WEIGHT) -> pd.DataFrame:
    """Суммы дней по часам: смесь формы последних недель и сезонной модели долей с весом model_weight."""
    shapes = {(r, k): data.shape(r, origin, k) for r in fold.route.unique() for k in LEVEL_DAYS}
    models = {r: data.model_shapes(r, origin) for r in fold.route.unique()} if model_weight > 0 else {}
    out = []
    for (r, d, k), total in zip(fold[["route", "date", "kind"]].itertuples(index=False), totals):
        shape = shapes[(r, k)]
        if model_weight > 0:
            shape = (1 - model_weight) * shape + model_weight * models[r][data.dates.get_loc(d)]
        out.append(pd.DataFrame({"route": r, "date": d, "hour": range(24), "pred": total * shape}))
    return pd.concat(out, ignore_index=True)


def score(data: Data, pred: pd.DataFrame, origin: pd.Timestamp, days: int) -> float:
    dates = pd.date_range(origin + pd.Timedelta(days=1), periods=days)
    truth = data.hourly.loc[(slice(None), dates), :].stack().rename("y").reset_index()
    truth.columns = ["route", "date", "hour", "y"]
    m = truth.merge(pred, on=["route", "date", "hour"], how="left").fillna({"pred": 0.0})
    return wape_score(m.y, m.pred)


def true_shares(data: Data, fold: pd.DataFrame) -> pd.DataFrame:
    h = data.hourly.reindex(pd.MultiIndex.from_frame(fold[["route", "date"]]))
    return h.div(h.sum(axis=1).replace(0, np.nan), axis=0).fillna(1 / 24)


def main() -> None:
    data = Data()
    rows = []
    for name, day, days in FOLDS:
        origin = pd.Timestamp(day)
        fold = frame(data, origin, days)
        seasonal = fold.level.to_numpy() * np.exp(fold.season.to_numpy())
        variants = {
            "profile": fold.level.to_numpy(),
            "season": seasonal,
            "regimes": fold.regime_level.to_numpy() * np.exp(fold.regime_season.to_numpy()),
            "oracle_level": data.daily.reindex(pd.MultiIndex.from_frame(fold[["route", "date"]])).fillna(0).to_numpy(),
        }
        res = {"fold": name, "v11": V11[name]}
        for label, totals in variants.items():
            res[label] = round(score(data, hourly(data, fold, origin, totals), origin, days), 6)
        shares = true_shares(data, fold).to_numpy()
        oracle_shape = fold[["route", "date"]].loc[fold.index.repeat(24)].assign(
            hour=np.tile(np.arange(24), len(fold)), pred=(seasonal[:, None] * shares).ravel())
        res["oracle_shape"] = round(score(data, oracle_shape, origin, days), 6)
        rows.append(res)
        print(res, flush=True)
    out = pd.DataFrame(rows)
    print(out.to_string(index=False))
    print("среднее", out.drop(columns="fold").mean().round(6).to_dict())
    out.to_csv(TABLES / "level_shape_folds.csv", index=False)


FUTURE_ORIGIN = "2025-10-31"
FUTURE_DAYS = 61
OUT = ROOT / "forecasts/submission_level_shape_v12.csv"


def future(data: Data) -> pd.DataFrame:
    """Прогноз ноября-декабря: уровень в режиме × сезон × правила календаря сервиса × форма суток.
    Правила, которых нет в истории, - значения ползунков сервиса по умолчанию (artifacts/coefficients.json):
    рабочая суббота, праздник в будний день, 29-30 и 31 декабря, бесплатный проезд с 20:00 31.12.
    Маршрут 5 в истории отсутствует, его прогноз берётся из честного s32 (submission_ex_ante_route5.csv)."""
    c = {k["key"]: k["default"] for k in json.loads((ROOT / "artifacts/coefficients.json").read_text(encoding="utf-8"))["coefficients"]}
    flags = pd.read_csv(ROOT / "artifacts/forecast_components.csv", usecols=["route", "date", "is_holiday",
        "is_working_saturday", "is_pre_new_year", "is_new_year_eve"], parse_dates=["date"]).drop_duplicates(["route", "date"])
    origin = pd.Timestamp(FUTURE_ORIGIN)
    fold = frame(data, origin, FUTURE_DAYS).merge(flags, on=["route", "date"], how="left")
    rule = np.where(fold.is_working_saturday == 1, c["working_saturday"], 1.0)
    rule *= np.where((fold.is_holiday == 1) & (fold.dow <= 4), c["holiday_to_sunday"], 1.0)
    rule *= np.where(fold.is_pre_new_year == 1, c["last_workdays_dec"], 1.0)
    rule *= np.where(fold.is_new_year_eve == 1, c["dec31_day"], 1.0)
    totals = fold.regime_level.to_numpy() * np.exp(fold.regime_season.to_numpy()) * rule
    pred = hourly(data, fold, origin, totals)
    eve = (pred.date == pd.Timestamp("2025-12-31")) & (pred.hour >= c["dec31_free_from_hour"])
    pred.loc[eve, "pred"] = 0.0
    r5 = pd.read_csv(ROOT / "forecasts/submission_ex_ante_route5.csv", sep=";", parse_dates=["date"])
    r5 = r5[r5.route == 5].rename(columns={"prediction": "pred"})
    out = pd.concat([pred, r5[["route", "date", "hour", "pred"]]], ignore_index=True)
    grid = pd.read_csv(ROOT / "dataset/test_submission.csv", sep=";", parse_dates=["date"])[["route", "date", "hour"]]
    out = grid.merge(out, on=["route", "date", "hour"], how="left", validate="one_to_one")
    assert len(out) == 14640 and out.pred.notna().all()
    return out.assign(prediction=np.rint(out.pred).astype("int64"), date=out.date.dt.strftime("%Y-%m-%d"))[
        ["route", "date", "hour", "prediction"]]


if __name__ == "__main__":
    if sys.argv[1:] == ["future"]:
        sub = future(Data())
        sub.to_csv(OUT, sep=";", index=False)
        print("записан", OUT.name, "сумма", int(sub.prediction.sum()))
    else:
        main()
