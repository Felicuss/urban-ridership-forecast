# Как собрать Москву из НСПД: аккуратный автоматический сбор

На выходе — таблица зданий Москвы с этажностью, назначением, годом ввода, материалом стен, кадастровой стоимостью и контуром, по желанию ещё участки, зоны, вода и кадастровые кварталы. Формат — parquet в EPSG:4326.

Старая Москва — 513 квадратов 2 × 2 км. Сборщик делает один запрос раз в 30 секунд, так что слой зданий собирается примерно за 4,5 часа, а всё целиком — за 10–11 часов фоном.

---

## 1. Что понадобится

- Python 3.10+ и пакеты `pandas`, `shapely`, `pyarrow`.
- Компьютер или сервер, который 10–11 часов не засыпает. Прогон можно разбить на несколько дней.
- До пары гигабайт на диске под сырые ответы: квадрат 2 км в центре Москвы — около 1200 зданий и 3,7 МБ, на окраинах меньше.

## 2. Доступ

Сборщик рассчитан на официальный доступ: API по соглашению с ППК «Роскадастр» (сервис «Встраиваемый картографический компонент ФГИС ЕЦП НСПД», выдают Client ID и Client Secret) или разрешение оператора на автоматические запросы. Для API по соглашению адрес и авторизацию возьмите из выданной документации и поменяйте в `Client.post`, остальное остаётся как есть. Плата зависит от числа объектов, расчёт просите заранее.

## 3. Сетка квадратов

Территорию режем на квадраты, привязанные к центру города. На рамке 2 км портал отдаёт всё одним ответом, для редких слоёв хватает 4 км.

```python
import math
import pandas as pd

LAT0, LON0 = 55.751, 37.618            # центр сетки
BBOX = (55.49, 55.96, 37.30, 37.90)    # lat_min, lat_max, lon_min, lon_max — старая Москва


def make_tiles(tile_m, prefix):
    dlat = tile_m / 111_320
    dlon = tile_m / (111_320 * math.cos(math.radians(LAT0)))
    i0, i1 = math.floor((BBOX[0] - LAT0) / dlat), math.floor((BBOX[1] - LAT0) / dlat)
    j0, j1 = math.floor((BBOX[2] - LON0) / dlon), math.floor((BBOX[3] - LON0) / dlon)
    rows = []
    for i in range(i0, i1 + 1):
        for j in range(j0, j1 + 1):
            la0, lo0 = LAT0 + i * dlat, LON0 + j * dlon
            rows.append({"tile_id": f"{prefix}_{i}_{j}", "lat_min": la0, "lat_max": la0 + dlat,
                         "lon_min": lo0, "lon_max": lo0 + dlon})
    return pd.DataFrame(rows)


t2, t4 = make_tiles(2000, "msk2"), make_tiles(4000, "msk4")
t2.to_csv("tiles_2km.csv", index=False)
t4.to_csv("tiles_4km.csv", index=False)
print(len(t2), len(t4))
```

Получится 513 квадратов по 2 км и 140 по 4 км. С Новой Москвой рамка `(55.10, 55.96, 36.80, 37.90)` даёт около 1700 квадратов по 2 км, но захватывает и область.

## 4. Слои

Сборщик запрашивает слои группами, одним запросом на квадрат.

| группа | сетка | слои (categoryId) |
|---|---|---|
| `view` | 2 км | здания 36369, ОНС 36384, сооружения 36383 |
| `parcels` | 2 км | участки 36368, выставленные на аукцион 38981, свободные 38979, по проекту межевания 37158 |
| `sparse` | 4 км | ЗОУИТ 36940, ООПТ 472825, ОКН 472820, лесопарки 472853, вода 472813 и 472816, кадастровые кварталы 36381, терр. зоны 472819 |

Начните с `view`, остальное добавляйте, когда здания пройдут проверку из раздела 8.

## 5. Как устроен сборщик

Код целиком — в приложении, файл `nspd_collect.py`.

**Темп и объём:**

- один процесс (файл-блокировка), один запрос за раз;
- от конца запроса до начала следующего не меньше 30 секунд — с самого первого, включая повторы и контрольные запросы. Время последнего запроса хранится в `state.json`, так что пауза соблюдается и после перезапуска;
- не больше 3000 запросов за скользящие сутки.

**Реакция на ответы:**

| ответ | что делает сборщик |
|---|---|
| 200, GeoJSON | пишет строку в `raw_<группа>.jsonl`, сбрасывает на диск, потом отмечает квадрат в `done_<группа>.txt` |
| 3000 объектов и больше | делит квадрат на 4, рекурсивно до 500 м; решение о дроблении запоминает |
| 429 | ждёт `Retry-After`, не меньше 15 минут, и удваивает паузу на сутки; второй 429 за сутки — остановка |
| 500, 502, 503, 504, таймаут, сеть | повтор через 2 и через 10 минут, потом квадрат в `failed_<группа>.txt` |
| 400, 413, 422 | квадрат в `failed` |
| любой другой код, HTML вместо JSON, другая схема ответа | остановка |

**Остановка:** сборщик пишет причину в `nspd_data/STOP` и выходит. Пока файл есть, он не делает ни одного запроса. Удаляет файл человек, когда разобрался. Пять квадратов подряд в `failed` — тоже остановка.

**Контрольный запрос:** в начале каждого запуска и раз в час — рамка 800 м в Академическом. Первый ответ становится эталоном (на 21.09.2026 там было 124 здания). Меньше 100 в первый раз или меньше 90% эталона потом — остановка: ответы стали неполными.

**Данные:** сведения о правах (`right_type`, `ownership_type`) вырезаются до записи на диск. Готовые квадраты повторно не запрашиваются, повторный запуск продолжает с места остановки.

## 6. Запуск по шагам

Положите в одну папку `nspd_collect.py`, `tiles_2km.csv`, `tiles_4km.csv`. В `USER_AGENT` впишите название проекта и контакт.

1. **Проверка — 3 квадрата.**
   ```bash
   python nspd_collect.py --group view --limit 3
   ```
   В `nspd_data/log.txt` должен быть контрольный запрос на ~124 здания и три квадрата с объектами. Откройте `raw_view.jsonl` и посмотрите на поля глазами.
2. **Пилот — 50 квадратов, около получаса.**
   ```bash
   python nspd_collect.py --group view --limit 50
   ```
   Прогоните разбор из раздела 7 и проверки из раздела 8 на этих данных.
3. **Полный прогон** — без `--limit`, по одной группе за раз:
   ```bash
   python nspd_collect.py --group view
   python nspd_collect.py --group parcels
   python nspd_collect.py --group sparse
   ```
   На Linux — фоном: `nohup python nspd_collect.py --group view > run_view.log 2>&1 &`. На Windows — отдельное окно терминала, сон компьютера выключить.
4. **Квадраты из `failed`** соберёт следующий запуск той же группы: они не отмечены готовыми.

Автоперезапуск по циклу или расписанию не ставьте: после остановки решает человек. Состояние смотрите по хвосту `log.txt` и числу строк в `done_<группа>.txt`.

| группа | квадратов | время |
|---|---|---|
| `view` | 513 | ~4,5 ч |
| `parcels` | 513 | ~4,5 ч |
| `sparse` | 140 | ~1,2 ч |

## 7. Разбор в таблицы

Ответ — GeoJSON FeatureCollection, геометрия **в EPSG:3857**, хотя запрос шёл в градусах. Пагинации нет.

```python
import glob
import json
import math

import pandas as pd
from shapely.geometry import shape
from shapely.ops import transform

R = 6378137.0
DROP = {"right_type", "ownership_type", "determination_couse"}   # права в таблицы не берём


def to_4326(x, y, z=None):
    return x / R * 180 / math.pi, math.degrees(math.atan(math.sinh(y / R)))


objs = {}
for path in sorted(glob.glob("nspd_data/raw_*.jsonl")):
    for line in open(path, encoding="utf-8"):
        for f in json.loads(line)["f"]:
            p = f.get("properties") or {}
            if not f.get("geometry"):
                continue
            key = (p.get("category"), f.get("id") or p.get("externalKey"))
            upd = ((p.get("systemInfo") or {}).get("updated") or "")[:10]
            # объект на стыке квадратов приходит дважды — оставляем свежую запись
            if key in objs and objs[key]["upd"] >= upd:
                continue
            opts = {k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                    for k, v in (p.get("options") or {}).items() if k not in DROP}
            objs[key] = {"cat": key[0], "obj_id": key[1], "cad": p.get("externalKey"), "upd": upd,
                         "opts": opts, "geom": f["geometry"]}

rows = []
for o in objs.values():
    g = transform(to_4326, shape(o["geom"]))   # ответ приходит в EPSG:3857
    c = g.representative_point()
    rows.append({"cat": o["cat"], "obj_id": o["obj_id"], "cad": o["cad"], "upd": o["upd"],
                 "lat": c.y, "lon": c.x, "wkt": g.wkt, **o["opts"]})
df = pd.DataFrame(rows)

b = df[df["cat"] == 36369].dropna(axis=1, how="all").copy()
# этажность бывает диапазоном «2-22» — берём максимум
b["floors_n"] = b["floors"].astype(str).str.findall(r"\d+").map(lambda x: max(map(int, x)) if x else None)
b = b.astype({col: "string" for col in b.columns if b[col].dtype == object and col != "floors_n"})
b.to_parquet("moscow_buildings.parquet", index=False)
print(len(b), "зданий, с этажностью", round(b["floors_n"].notna().mean(), 3))
```

Остальные слои сохраняются так же, фильтром по `cat`.

### Поля зданий (категория 36369)

| поле | что это |
|---|---|
| `floors`, `underground_floors` | этажность, подземные этажи |
| `purpose` | «Многоквартирный дом», «Жилой дом», «Нежилое» |
| `year_built`, `year_commisioning` | год постройки и ввода |
| `materials` | материал стен |
| `build_record_area` | площадь по ЕГРН, м² |
| `cost_value`, `cost_index` | кадастровая стоимость, ₽, и она же за м² |
| `cad_num`, `quarter_cad_number` | кадастровый номер здания и квартала |
| `readable_address` | адрес строкой |

У участков (36368) площадь разнесена по трём полям: склеивайте по приоритету `land_record_area` → `specified_area` → `declared_area`.

## 8. Проверка качества

- **Этажность.** По Москве заполнена почти у всех зданий. Меньше 95% — где-то потеряли ответы.
- **Ноль — не пропуск, но и не значение.** У ОНС и сооружений высота, объём и площадь часто равны нулю. Нули считайте отдельно от пустых.
- **Полнота контуров.** Кадастровый квартал (36381) отдаёт `cnt_oks` и `cnt_oks_geom` — сколько объектов в квартале и у скольких есть контур. В Москве контур бывает только у половины. Сравните `cnt_oks_geom` с числом зданий, которые у вас есть по этому кварталу: так видно, что потеряли вы, а чего нет у самого источника.
- **Покрытие.** Нанесите центры зданий на карту поверх сетки: пустые квадраты посреди застройки — это квадраты из `failed`.
- **Дробления.** Квадраты из `split_<группа>.txt` — самые плотные; проверьте, что все их части есть в `done`.

## 9. Чек-лист

- [ ] доступ есть, в `USER_AGENT` название проекта и контакт
- [ ] сетка построена: `tiles_2km.csv`, `tiles_4km.csv`
- [ ] проверка на 3 квадратах и пилот на 50 прошли, данные посмотрены глазами
- [ ] полный прогон по группам, без автоперезапуска
- [ ] `failed` пуст или добран повторным запуском
- [ ] разбор: дубли сняты, геометрия в EPSG:4326, права вырезаны
- [ ] проверки из раздела 8 пройдены

---

## Приложение: `nspd_collect.py`

```python
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

URL = "https://nspd.gov.ru/api/geoportal/v1/intersects?typeIntersect=fullObject"
USER_AGENT = "my-project/1.0 (contact: me@example.com)"   # своё название и контакт
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
        self.st["reqs"].append(time.time())
        self.save()
        req = urllib.request.Request(URL, data=payload(box, cats), method="POST", headers={
            "User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json"})
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
                    raise Stop("ответ 200, но не JSON — возможна капча или заглушка: " + raw[:200].decode("utf-8", "ignore"))
                if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
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
                log(f"    {tid}: {len(feats)} объектов на минимальной рамке, записан как есть")
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
```
