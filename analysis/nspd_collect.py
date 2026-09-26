# -*- coding: utf-8 -*-
"""Аккуратный сборщик НСПД по сетке квадратов.

  python nspd_collect.py --group view --limit 3     # проверка
  python nspd_collect.py --group view --limit 50    # пилот
  python nspd_collect.py --group view               # полный прогон
"""
import argparse
import datetime as dt
import email.utils
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

import pandas as pd

URL = os.environ.get("NSPD_API_URL", "https://nspd.gov.ru/api/geoportal/v1/intersects?typeIntersect=fullObject")
USER_AGENT = os.environ.get("NSPD_USER_AGENT", "tram-forecast/1.0 (project: https://github.com/Mojarung/hakaton_moskovskogo_transporta_2026)")
GROUPS = {
    "view": [36369, 36384, 36383],                    # здания, ОНС, сооружения
    "parcels": [36368, 38981, 38979, 37158],          # участки
    "sparse": [36940, 472825, 472820, 472853, 472813, 472816, 36381, 472819],  # зоны, вода, кварталы
}
MIN_PAUSE_S = 30            # от конца запроса до начала следующего, всегда
MAX_REQ_24H = 3000
TIMEOUT_S = 60
RETRY_DELAYS_S = (120, 600)  # сбой сервера или сети: два повтора, потом квадрат в failed
TRANSIENT = {500, 502, 503, 504}
SPLIT_AT = 3000
MIN_SIDE_M = 500
FAIL_STREAK = 5
CANARY_EVERY_S = 3600
CANARY_BOX = (55.6770, 55.6842, 37.5692, 37.5820)   # ~800 м, Академический
CANARY_MIN_REF, CANARY_MIN_RATIO = 100, 0.9
RIGHTS = {"right_type", "ownership_type", "determination_couse"}
M_PER_DEG = 111_320.0


class Stop(Exception):
    """Остановка до решения человека."""


def payload(box, cats):
    lat_min, lat_max, lon_min, lon_max = box
    ring = [[lon_min, lat_min], [lon_max, lat_min], [lon_max, lat_max], [lon_min, lat_max], [lon_min, lat_min]]
    geom = {"type": "Polygon", "coordinates": [ring], "crs": {"type": "name", "properties": {"name": "EPSG:4326"}}}
    return json.dumps({"categories": [{"id": c} for c in cats],
                       "geom": {"type": "FeatureCollection",
                                "features": [{"type": "Feature", "properties": {}, "geometry": geom}]}}).encode()


def strip_rights(o):
    if isinstance(o, dict):
        return {k: strip_rights(v) for k, v in o.items() if k not in RIGHTS}
    if isinstance(o, list):
        return [strip_rights(v) for v in o]
    return o


def split4(box):
    a, b, c, d = box
    m, n = (a + b) / 2, (c + d) / 2
    return [(a, m, c, n), (a, m, n, d), (m, b, c, n), (m, b, n, d)]


def side_m(box):
    return (box[1] - box[0]) * M_PER_DEG


class Client:
    """Единственный путь к порталу: пауза, суточный потолок, учёт между запусками."""

    def __init__(self, out, log):
        self.out, self.log = out, log
        self.state_path = os.path.join(out, "state.json")
        self.st = {"last_end": 0.0, "reqs": [], "slow_until": 0.0, "last_429": 0.0,
                   "canary_ref": None, "canary_at": 0.0}
        if os.path.exists(self.state_path):
            self.st.update(json.load(open(self.state_path, encoding="utf-8")))

    def save(self):
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.st, fh)
        os.replace(tmp, self.state_path)

    def _wait(self):
        now = time.time()
        self.st["reqs"] = [t for t in self.st["reqs"] if now - t < 86400]
        if len(self.st["reqs"]) >= MAX_REQ_24H:
            wait = self.st["reqs"][0] + 86400 - now + 1
            self.log(f"суточный потолок, сон {wait / 3600:.1f} ч")
            time.sleep(wait)
        pause = MIN_PAUSE_S * (2 if now < self.st["slow_until"] else 1)
        left = self.st["last_end"] + pause - time.time()
        if left > 0:
            time.sleep(left)

    def post(self, box, cats):
        """Один запрос: (код или None при сбое сети, заголовки, тело)."""
        if os.path.exists(os.path.join(self.out, "STOP")):
            raise Stop("есть файл STOP")
        self._wait()
        if os.path.exists(os.path.join(self.out, "STOP")):
            raise Stop("есть файл STOP")
        self.st["reqs"].append(time.time())
        self.save()
        req = urllib.request.Request(URL, data=payload(box, cats), method="POST", headers={
            "User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json",
            **({"Authorization": "Bearer " + os.environ["NSPD_ACCESS_TOKEN"]} if os.environ.get("NSPD_ACCESS_TOKEN") else {})})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            return None, {}, str(e).encode()
        finally:
            self.st["last_end"] = time.time()
            self.save()

    def on_429(self, headers):
        now = time.time()
        if now - self.st["last_429"] < 86400:
            raise Stop("второй 429 за сутки")
        self.st["last_429"], self.st["slow_until"] = now, now + 86400
        self.save()
        ra = (headers or {}).get("Retry-After")
        wait = 900
        if ra:
            if ra.strip().isdigit():
                wait = max(wait, int(ra))
            else:
                t = email.utils.parsedate_to_datetime(ra)
                wait = max(wait, t.timestamp() - now) if t else wait
        self.log(f"429: сон {wait / 60:.0f} мин, пауза ×2 на сутки")
        time.sleep(wait)

    def fetch(self, box, cats):
        """Объекты рамки; 'split' — рамка тяжёлая; None — квадрат не прошёл."""
        attempt = 0
        while True:
            status, headers, raw = self.post(box, cats)
            if status == 200:
                try:
                    data = json.loads(raw.decode("utf-8"))
                except ValueError:
                    raise Stop("ответ 200, но не JSON — возможна капча или заглушка: " + "неожиданный формат")
                if not isinstance(data, dict) or data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
                    raise Stop("изменилась схема ответа")
                return data["features"]
            if status == 429:
                self.on_429(headers)
                continue
            if status in TRANSIENT and b"400104" in raw:
                return "split"
            if status in (400, 413, 422):
                self.log(f"    HTTP {status}: {raw[:200].decode('utf-8', 'ignore')}")
                return None
            if status is not None and status not in TRANSIENT:
                raise Stop(f"HTTP {status}: {raw[:200].decode('utf-8', 'ignore')}")
            if attempt == len(RETRY_DELAYS_S):
                return None
            self.log(f"    сбой ({status or raw[:120].decode('utf-8', 'ignore')}), повтор через {RETRY_DELAYS_S[attempt]} с")
            time.sleep(RETRY_DELAYS_S[attempt])
            attempt += 1

    def canary(self, force=False):
        """Контрольный запрос: портал отдаёт столько же, сколько в первый раз."""
        if not force and time.time() - self.st["canary_at"] < CANARY_EVERY_S:
            return
        feats = self.fetch(CANARY_BOX, [36369])
        if not isinstance(feats, list):
            raise Stop("контрольный запрос не прошёл")
        ref = self.st["canary_ref"]
        if ref is None:
            if len(feats) < CANARY_MIN_REF:
                raise Stop(f"контрольный запрос: {len(feats)} зданий, ожидалось от {CANARY_MIN_REF}")
            self.st["canary_ref"] = ref = len(feats)
        elif len(feats) < CANARY_MIN_RATIO * ref:
            raise Stop(f"контрольный запрос: {len(feats)} зданий против эталона {ref}")
        self.st["canary_at"] = time.time()
        self.save()
        self.log(f"контрольный запрос: {len(feats)} зданий (эталон {ref})")


def read_ids(path):
    return set(open(path, encoding="utf-8").read().split()) if os.path.exists(path) else set()


def append(path, line, sync=False):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        if sync:
            fh.flush()
            os.fsync(fh.fileno())


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", choices=list(GROUPS), default="view")
    ap.add_argument("--tiles", default="", help="по умолчанию tiles_4km.csv для sparse, иначе tiles_2km.csv")
    ap.add_argument("--out", default="nspd_data")
    ap.add_argument("--limit", type=int, default=0, help="не больше N квадратов за запуск")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    tiles_path = a.tiles or ("tiles_4km.csv" if a.group == "sparse" else "tiles_2km.csv")
    cats = GROUPS[a.group]
    p = {k: os.path.join(a.out, f"{k}_{a.group}.txt") for k in ("done", "failed", "split")}
    raw_path = os.path.join(a.out, f"raw_{a.group}.jsonl")
    log_path = os.path.join(a.out, "log.txt")

    def log(msg):
        line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
        print(line, flush=True)
        append(log_path, line)

    lock = os.path.join(a.out, "collect.lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        sys.exit(f"уже запущен другой сборщик; если процесса нет — удалите {lock}")
    os.close(fd)
    cl = Client(a.out, log)
    done, split = read_ids(p["done"]), read_ids(p["split"])
    fails = 0

    def collect(tid, box):
        """Квадрат целиком: при тяжёлой рамке — по четвертям, рекурсивно до MIN_SIDE_M."""
        nonlocal fails
        if tid in done:
            return True
        feats = "split" if tid in split else cl.fetch(box, cats)
        if isinstance(feats, list) and (len(feats) < SPLIT_AT or side_m(box) / 2 < MIN_SIDE_M):
            if len(feats) >= SPLIT_AT:
                raise Stop(f"{tid}: {len(feats)} объектов на минимальной рамке; полнота не подтверждена")
            rec = {"tile": tid, "ts": dt.datetime.now().isoformat(timespec="seconds"), "n": len(feats),
                   "f": strip_rights(feats)}
            append(raw_path, json.dumps(rec, ensure_ascii=False, separators=(",", ":")), sync=True)
            append(p["done"], tid)   # отметка только после записи данных на диск
            done.add(tid)
            fails = 0
            log(f"  {tid}: {len(feats)} объектов")
            return True
        if feats is None:
            append(p["failed"], f"{tid}\t{dt.datetime.now().isoformat(timespec='seconds')}")
            fails += 1
            log(f"  {tid}: не прошёл, в failed ({fails} подряд)")
            if fails >= FAIL_STREAK:
                raise Stop(f"{fails} квадратов подряд не прошли")
            return False
        if side_m(box) / 2 < MIN_SIDE_M:
            raise Stop(f"{tid}: рамка тяжёлая на минимальном размере; полнота не подтверждена")
        if tid not in split:
            append(p["split"], tid)
            split.add(tid)
            log(f"  {tid}: рамка тяжёлая, делю на 4")
        ok = all([collect(f"{tid}/{k}", sub) for k, sub in enumerate(split4(box), 1)])
        if ok:
            append(p["done"], tid)
            done.add(tid)
        return ok

    try:
        tiles = pd.read_csv(tiles_path)
        todo = tiles[~tiles["tile_id"].isin(done)]
        if a.limit:
            todo = todo.head(a.limit)
        log(f"[{a.group}] к сбору {len(todo)} квадратов, готово раньше {len(done)}")
        cl.canary(force=True)
        for t in todo.itertuples(index=False):
            cl.canary()
            collect(t.tile_id, (t.lat_min, t.lat_max, t.lon_min, t.lon_max))
        log(f"[{a.group}] запуск завершён")
    except Stop as e:
        with open(os.path.join(a.out, "STOP"), "w", encoding="utf-8") as fh:
            fh.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {e}\n")
        log(f"ОСТАНОВКА: {e}. Разобраться, удалить {os.path.join(a.out, 'STOP')} и запустить снова")
        sys.exit(3)
    finally:
        os.remove(lock)


if __name__ == "__main__":
    main()
