"""Сырые train.csv/test.csv (10.4 ГБ) -> один parquet с типизированными полями.

Все поля читаем строками и приводим через TRY_CAST: так битые значения
превращаются в NULL и их можно посчитать, а не уронить загрузку.
Запуск: uv run python analysis/s00_prepare_parquet.py
"""

import time

from common import DATASET, RAW_PARQUET, connect

SOURCES = {"train": DATASET / "train.csv", "test": DATASET / "test.csv"}


def main() -> None:
    con = connect()
    selects = []
    for split, path in SOURCES.items():
        selects.append(f"""
            SELECT
                '{split}' AS split,
                TRY_CAST(tran_no AS BIGINT) AS tran_no,
                TRY_CAST(device_no AS BIGINT) AS device_no,
                TRY_CAST(tran_date_time AS TIMESTAMP) AS tran_ts,
                TRY_CAST(begin_date_time AS TIMESTAMP) AS begin_ts,
                TRY_CAST(input_date_time AS TIMESTAMP) AS input_ts,
                tran_date_time AS tran_date_time_raw,
                crd_hashcode,
                TRY_CAST(validation_result AS INTEGER) AS validation_result,
                TRY_CAST(tran_type_id AS INTEGER) AS tran_type_id,
                TRY_CAST(place_id AS INTEGER) AS place_id,
                good_type,
                pass_route,
                ngpt_route,
                TRY_CAST(regexp_extract(ngpt_route, '^\\s*(\\d+)', 1) AS INTEGER) AS route,
                bus_exit_no,
                garage_number
            FROM read_csv('{path.as_posix()}', delim=';', header=true, all_varchar=true,
                          quote='"', strict_mode=false, parallel=false)
        """)
    query = " UNION ALL ".join(selects)
    t0 = time.time()
    con.execute(f"""
        COPY ({query}) TO '{RAW_PARQUET.as_posix()}'
        (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 1000000)
    """)
    n = con.execute(f"SELECT count(*) FROM '{RAW_PARQUET.as_posix()}'").fetchone()[0]
    print(f"rows={n:,} time={time.time() - t0:.0f}s -> {RAW_PARQUET}")


if __name__ == "__main__":
    main()
