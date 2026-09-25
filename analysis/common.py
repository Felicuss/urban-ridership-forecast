"""Общие пути и хелперы для скриптов анализа."""

from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset"
DATA = ROOT / "data"
FIGURES = ROOT / "docs" / "analysis" / "figures"
TABLES = ROOT / "docs" / "analysis" / "tables"

RAW_PARQUET = DATA / "validations.parquet"
ROUTES = [1, 5, 7, 11, 12, 17, 25, 26, 28, 50]

TRAIN_START, TRAIN_END = "2025-01-01", "2025-08-31"
TEST_START, TEST_END = "2025-09-01", "2025-10-31"
FORECAST_START, FORECAST_END = "2025-11-01", "2025-12-31"

for p in (DATA, FIGURES, TABLES):
    p.mkdir(parents=True, exist_ok=True)

# Палитра из скилла dataviz (светлая тема): фиксированный порядок слотов, не циклим.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
MUTED = "#a8a7a2"
DIVERGING = ("#2a78d6", "#f0efec", "#e34948")

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": TEXT_SECONDARY,
        "axes.titlecolor": TEXT_PRIMARY,
        "axes.titlesize": 11,
        "axes.titleweight": "semibold",
        "axes.labelsize": 9,
        "axes.grid": True,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.prop_cycle": plt.cycler(color=SERIES),
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "grid.linestyle": "-",
        "xtick.color": TEXT_SECONDARY,
        "ytick.color": TEXT_SECONDARY,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "legend.frameon": False,
        "lines.linewidth": 1.4,
        "font.family": "DejaVu Sans",
        "figure.titlesize": 13,
        "figure.titleweight": "semibold",
    }
)

ACTIVE_ROUTES = [r for r in ROUTES if r != 5]  # маршрут 5 в labels отсутствует


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET threads TO 12")
    con.execute("SET memory_limit = '20GB'")
    return con


def load_labels() -> pd.DataFrame:
    """Почасовые посадки от организаторов (train + test) на полной сетке 24 часа.

    В файлах labels нет строк для часов без посадок, поэтому сетку достраиваем нулями.
    """
    parts = []
    for name in ("labels_day_train.csv", "labels_day_test.csv"):
        parts.append(pd.read_csv(DATASET / "labels" / name, sep=";", parse_dates=["date"]))
    df = pd.concat(parts, ignore_index=True)
    grid = pd.MultiIndex.from_product(
        [ROUTES, pd.date_range(TRAIN_START, TEST_END, freq="D"), range(24)],
        names=["route", "date", "hour"],
    ).to_frame(index=False)
    df = grid.merge(df, on=["route", "date", "hour"], how="left")
    df["boardings"] = df["boardings"].fillna(0).astype("int64")
    df["ts"] = df["date"] + pd.to_timedelta(df["hour"], unit="h")
    return df


def wape(y_true, y_pred) -> float:
    y_true = pd.Series(y_true, dtype="float64").to_numpy()
    y_pred = pd.Series(y_pred, dtype="float64").to_numpy()
    return float(abs(y_true - y_pred).sum() / y_true.sum())


def wape_score(y_true, y_pred) -> float:
    return max(0.0, 1.0 - wape(y_true, y_pred))


def savefig(fig: plt.Figure, name: str) -> Path:
    path = FIGURES / f"{name}.png"
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return path
