"""Качество сырых валидаций и проверка, как организаторы построили labels.

Запуск: uv run python analysis/s03_raw_quality.py
"""

import pandas as pd

from common import DATA, RAW_PARQUET, TABLES, connect, load_labels

P = f"'{RAW_PARQUET.as_posix()}'"


def q(con, sql: str) -> pd.DataFrame:
    return con.execute(sql).df()


def main() -> None:
    con = connect()
    pd.set_option("display.width", 220)
    pd.set_option("display.max_rows", 200)

    print("== объём и диапазоны дат по split ==")
    print(q(con, f"""
        SELECT split, count(*) AS rows,
               min(tran_ts) AS min_ts, max(tran_ts) AS max_ts,
               count(*) FILTER (tran_ts IS NULL) AS tran_ts_null,
               count(*) FILTER (begin_ts IS NULL) AS begin_ts_null,
               count(*) FILTER (input_ts IS NULL) AS input_ts_null,
               count(*) FILTER (input_ts < '2025-01-01' OR input_ts >= '2026-01-01') AS input_ts_out_2025,
               count(*) FILTER (input_ts < tran_ts) AS input_before_tran
        FROM {P} GROUP BY split ORDER BY split"""))

    print("== хвосты: строки split, попавшие в чужой месяц ==")
    print(q(con, f"""
        SELECT split, strftime(tran_ts, '%Y-%m') AS ym, count(*) AS rows
        FROM {P}
        WHERE (split = 'train' AND tran_ts >= '2025-09-01') OR (split = 'test' AND tran_ts >= '2025-11-01')
           OR (split = 'test' AND tran_ts < '2025-09-01')
        GROUP BY ALL ORDER BY ALL"""))

    print("== validation_result ==")
    vr = q(con, f"""
        SELECT validation_result, count(*) AS rows, round(100.0 * count(*) / sum(count(*)) OVER (), 3) AS pct
        FROM {P} GROUP BY 1 ORDER BY rows DESC""")
    print(vr)
    vr.to_csv(TABLES / "validation_result.csv", index=False)

    print("== tran_type_id ==")
    tt = q(con, f"""
        SELECT tran_type_id, count(*) AS rows,
               round(100.0 * count(*) FILTER (validation_result = 1) / count(*), 2) AS success_pct,
               round(100.0 * count(*) / sum(count(*)) OVER (), 3) AS pct
        FROM {P} GROUP BY 1 ORDER BY rows DESC""")
    print(tt)
    tt.to_csv(TABLES / "tran_type_id.csv", index=False)

    print("== ngpt_route ==")
    rt = q(con, f"""
        SELECT ngpt_route, route, count(*) AS rows, count(*) FILTER (validation_result = 1) AS ok,
               min(tran_ts)::DATE AS first_day, max(tran_ts)::DATE AS last_day,
               count(DISTINCT tran_ts::DATE) AS days
        FROM {P} GROUP BY 1, 2 ORDER BY rows DESC""")
    print(rt)
    rt.to_csv(TABLES / "ngpt_route.csv", index=False)

    print("== place_id по маршрутам (успешные) ==")
    print(q(con, f"""
        SELECT route, place_id, count(*) AS ok FROM {P}
        WHERE validation_result = 1 GROUP BY 1, 2 ORDER BY 1, 3 DESC""").to_string())

    print("== дубли ==")
    print(q(con, f"""
        SELECT
          (SELECT count(*) FROM (SELECT tran_no, device_no, tran_ts, crd_hashcode, count(*) c FROM {P}
                                 GROUP BY ALL HAVING c > 1)) AS dup_groups_full_key,
          (SELECT sum(c - 1) FROM (SELECT tran_no, device_no, tran_ts, crd_hashcode, count(*) c FROM {P}
                                   GROUP BY ALL HAVING c > 1)) AS dup_extra_rows,
          (SELECT sum(c - 1) FROM (SELECT tran_no, device_no, count(*) c FROM {P}
                                   GROUP BY ALL HAVING c > 1)) AS dup_extra_rows_tranno_device"""))

    print("== повторные валидации одной карты в одном вагоне за 60 секунд (успешные) ==")
    print(q(con, f"""
        WITH ok AS (
            SELECT crd_hashcode, garage_number, tran_ts,
                   lag(tran_ts) OVER (PARTITION BY crd_hashcode, garage_number ORDER BY tran_ts) AS prev_ts
            FROM {P} WHERE validation_result = 1 AND crd_hashcode IS NOT NULL
        )
        SELECT count(*) AS ok_rows,
               count(*) FILTER (date_diff('second', prev_ts, tran_ts) <= 60) AS repeat_60s,
               round(100.0 * count(*) FILTER (date_diff('second', prev_ts, tran_ts) <= 60) / count(*), 2) AS pct
        FROM ok"""))

    print("== воспроизводим labels: count(validation_result = 1) по route, дата, час из tran_ts ==")
    mine = q(con, f"""
        SELECT route, tran_ts::DATE AS date, hour(tran_ts) AS hour, count(*) AS mine
        FROM {P}
        WHERE validation_result = 1 AND tran_ts >= '2025-01-01' AND tran_ts < '2025-11-01'
        GROUP BY ALL""")
    mine["date"] = pd.to_datetime(mine["date"])
    lab = load_labels()
    cmp_ = lab.merge(mine, on=["route", "date", "hour"], how="outer")
    cmp_[["boardings", "mine"]] = cmp_[["boardings", "mine"]].fillna(0)
    cmp_["diff"] = cmp_["mine"] - cmp_["boardings"]
    print(f"cells={len(cmp_)} exact={(cmp_['diff'] == 0).mean():.4%} "
          f"sum_labels={cmp_['boardings'].sum():,.0f} sum_mine={cmp_['mine'].sum():,.0f}")
    bad = cmp_[cmp_["diff"] != 0]
    print("mismatches by route:\n", bad.groupby("route")["diff"].agg(["count", "sum"]))
    print(bad.sort_values("diff").head(10))

    print("== route 5: где и когда ==")
    print(q(con, f"""
        SELECT tran_ts::DATE AS d, validation_result, count(*) AS rows, any_value(garage_number) AS garage,
               any_value(place_id) AS place
        FROM {P} WHERE route = 5 GROUP BY ALL ORDER BY d LIMIT 40""").to_string())

    print("== нулевые/пустые ключевые поля (успешные) ==")
    print(q(con, f"""
        SELECT count(*) FILTER (crd_hashcode IS NULL OR crd_hashcode = '') AS no_card,
               count(*) FILTER (garage_number IS NULL OR garage_number = '') AS no_garage,
               count(*) FILTER (bus_exit_no IS NULL OR bus_exit_no = '') AS no_exit,
               count(*) FILTER (route IS NULL) AS no_route
        FROM {P} WHERE validation_result = 1"""))

    # Агрегаты для дальнейшего анализа: предложение (вагоны, выходы) и спрос по дням и часам.
    con.execute(f"""
        COPY (
            SELECT route, tran_ts::DATE AS date, hour(tran_ts) AS hour,
                   count(*) FILTER (validation_result = 1) AS boardings,
                   count(*) FILTER (validation_result <> 1) AS rejects,
                   count(DISTINCT garage_number) FILTER (validation_result = 1) AS vehicles,
                   count(DISTINCT bus_exit_no) FILTER (validation_result = 1) AS exits,
                   count(DISTINCT crd_hashcode) FILTER (validation_result = 1) AS cards
            FROM {P}
            WHERE tran_ts >= '2025-01-01' AND tran_ts < '2025-11-01' AND route IS NOT NULL
            GROUP BY ALL
        ) TO '{(DATA / "route_hour_agg.parquet").as_posix()}' (FORMAT parquet)""")
    con.execute(f"""
        COPY (
            SELECT route, tran_ts::DATE AS date,
                   count(*) FILTER (validation_result = 1) AS boardings,
                   count(DISTINCT garage_number) FILTER (validation_result = 1) AS vehicles,
                   count(DISTINCT bus_exit_no) FILTER (validation_result = 1) AS exits,
                   count(DISTINCT crd_hashcode) FILTER (validation_result = 1) AS cards
            FROM {P}
            WHERE tran_ts >= '2025-01-01' AND tran_ts < '2025-11-01' AND route IS NOT NULL
            GROUP BY ALL
        ) TO '{(DATA / "route_day_agg.parquet").as_posix()}' (FORMAT parquet)""")
    print("aggregates saved")


if __name__ == "__main__":
    main()
