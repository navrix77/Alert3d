"""«Мапа доби»: траєкторії всіх цілей і місця вибухів за добу 09:00 → 09:00 (Київ).

Збирається постфактум із журналу повідомлень (brain.msg): усі повідомлення доби повторно проганяються через
окремий «тіньовий» трекер, і щохвилини фіксується, де була кожна ціль. Звідси — повні маршрути, навіть після
перезапуску сервера. Вибухи/прильоти беремо з повідомлень, які вживу приховує фільтр безпеки:
на мапі доби вони показуються лише після завершення доби і лише з точністю до населеного пункту.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import re
import time
from pathlib import Path

log = logging.getLogger("daily")
VER = 5
OUT = (Path(__import__("os").environ["PERSIST_DIR"]) / "daily") if __import__("os").environ.get("PERSIST_DIR") else Path(__file__).resolve().parent.parent / "data" / "daily"
BOOM = re.compile(r"вибух|взрыв|прил[іеё]т|влучан|попадан|детонац|пожеж|уламк|обломк|пошкодж|поврежд|руйнув|зруйн|постраждал|пострадал|загинул|загибл|поранен")
# лише робота ППО без жодних наслідків — не «приліт»
PPO_ONLY = re.compile(r"збит|сбит|мінус|минус|ппо|пво|не фіксу|відбій|історі|рік тому|роковин")
DAMAGE = re.compile(r"уламк|обломк|пошкодж|поврежд|руйнув|зруйн|постраждал|пострадал|загинул|загибл|поранен|пожеж|влучан|приліт|прил[её]т|попадан")
NOT_BOOM = PPO_ONLY  # сумісність
CAPITAL = {"Київська": "Київ", "Харківська": "Харків", "Сумська": "Суми", "Полтавська": "Полтава", "Дніпропетровська": "Дніпро",
           "Запорізька": "Запоріжжя", "Одеська": "Одеса", "Миколаївська": "Миколаїв", "Херсонська": "Херсон", "Чернігівська": "Чернігів",
           "Черкаська": "Черкаси", "Житомирська": "Житомир", "Вінницька": "Вінниця", "Хмельницька": "Хмельницький", "Львівська": "Львів",
           "Волинська": "Луцьк", "Рівненська": "Рівне", "Тернопільська": "Тернопіль", "Івано-Франківська": "Івано-Франківськ",
           "Чернівецька": "Чернівці", "Кіровоградська": "Кропивницький", "Донецька": "Краматорськ", "Закарпатська": "Ужгород"}


COMMON = {"Українка", "Українець", "Зелень", "Середи", "Слава", "Сіль", "Вороне", "Кушніри", "Мирне", "Миру", "Світло", "Вогні",
          "Нова Гута", "Росільна", "Щасливе", "Тиха", "Робота", "Удар", "Дача", "Поле", "Вишневе"}


_TR = str.maketrans("єїЄЇ", "ііІІ")


class CAPMID:
    """Назва з великої літери не на початку речення (з урахуванням відмінків: Київ → у Києві)."""
    def __init__(self, stem: str):
        st = stem.translate(_TR)
        self.rx = re.compile(r"(?<![.!?…»\n]\s)(?<!^)(?<!\n)\b" + re.escape(st[0].upper() + st[1:]))

    def search(self, text: str):
        return self.rx.search(text.translate(_TR))


def is_impact(low: str) -> bool:
    if not BOOM.search(low):
        return False
    return bool(DAMAGE.search(low)) or not PPO_ONLY.search(low)


async def crawl_impacts(t0: float, t1: float, parser, max_pages: int = 40) -> list[dict]:
    """Повна історія ВСІХ каналів за добу (новини, міські й регіональні канали) — саме там пишуть «у Києві вибухи»,
    «уламки впали», «пошкоджено». Сторінки t.me/s/…?before=, чемно й паралельно по 6 каналів."""
    import httpx
    from . import config
    from .parser import CHANNEL_CITY
    from .tg_web import UA, parse_page
    reg_of = config.CHANNEL_REGION
    found: list[tuple[float, str, str, str]] = []
    sem = asyncio.Semaphore(8)

    async def one(cli, key, user):
        before = None
        async with sem:
            for _ in range(max_pages):
                try:
                    r = await cli.get(f"https://t.me/s/{user}" + (f"?before={before}" if before else ""))
                    msgs = parse_page(r.text)
                except Exception:  # noqa: BLE001
                    return
                if not msgs:
                    return
                for mid, ts, text in msgs:
                    if t0 <= ts < t1 and is_impact((text or "").lower()):
                        found.append((ts, text, key, f"https://t.me/{user}/{mid}"))
                before = min(m[0] for m in msgs)
                if min(m[1] for m in msgs) < t0:
                    return
                await asyncio.sleep(0.4)
    async with httpx.AsyncClient(timeout=20, headers=UA, follow_redirects=True) as cli:
        await asyncio.gather(*(one(cli, k, u) for k, u, *_ in config.CHANNELS))
    booms: dict[str, dict] = {}
    for ts, text, key, link in sorted(found):
        low = text.lower()
        try:
            o = parser.parse(text, key)
        except Exception:  # noqa: BLE001
            continue
        pl = [r.place for r in o.places if r.role in ("p", "t")][:2]
        if not pl:
            city = CHANNEL_CITY.get(key) or CAPITAL.get(reg_of.get(key, ""))
            if city:
                ids = parser.gaz.lookup(city)
                if ids:
                    pl = [max((parser.gaz.places[i] for i in ids), key=lambda q: q.pop)]
        for p in pl:
            if not (44 <= p.lat <= 52.5 and 22 <= p.lon <= 40.3) or p.name in COMMON:
                continue
            base = p.name.split(" (")[0]
            stem = base[:max(3, len(base) - 2)]
            # назва має стояти в тексті з великої літери не на початку речення — інакше це звичайне слово
            # («українці», «зелень», «Слава Україні»); виняток — місто каналу, підставлене без згадки
            if p.kind != "D" and not CAPMID(stem).search(text) and p.name not in (CHANNEL_CITY.get(key), CAPITAL.get(reg_of.get(key, ""))):
                continue
            b = booms.setdefault(p.name, {"n": p.name, "lat": p.lat, "lon": p.lon, "c": 0, "t": int(ts), "last": 0, "srcs": set(), "links": [], "pop": p.pop})
            if ts - b["last"] > 600:  # одна подія = повідомлення різних каналів у межах 10 хв
                b["c"] += 1
            b["last"] = ts
            b["srcs"].add(key)
            if len(b["links"]) < 3:
                b["links"].append(link)
    # село з одним джерелом — надто ненадійно (тезки, загальні слова); місто або ≥2 незалежні канали — так
    return [{"n": b["n"], "lat": b["lat"], "lon": b["lon"], "c": b["c"], "t": b["t"], "src": len(b["srcs"]), "links": b["links"]}
            for b in booms.values() if b["pop"] >= 20000 or len(b["srcs"]) >= 2]
SHOT = re.compile(r"збито/подавлено\s+(\d+)")


def kyiv_offset(t: float) -> int:
    """UTC+3 з останньої неділі березня до останньої неділі жовтня (01:00 UTC), інакше UTC+2 — без tzdata."""
    d = dt.datetime.fromtimestamp(t, dt.timezone.utc)

    def last_sun(m: int) -> dt.datetime:
        x = dt.datetime(d.year, m, 31, 1, tzinfo=dt.timezone.utc)
        return x - dt.timedelta(days=(x.weekday() + 1) % 7)
    return 3 if last_sun(3) <= d < last_sun(10) else 2


def window(day: str) -> tuple[float, float]:
    """day = дата РАНКУ, коли доба закінчується (YYYY-MM-DD): від 09:00 попереднього дня до 09:00 цього."""
    y, m, d = map(int, day.split("-"))
    end_local = dt.datetime(y, m, d, 9, 0, tzinfo=dt.timezone.utc)
    t1 = end_local.timestamp() - kyiv_offset(end_local.timestamp()) * 3600
    t0 = t1 - 24 * 3600
    return t0, t1


def current_day(now: float | None = None) -> str:
    """Доба, яка зараз триває (дата її ранку о 09:00)."""
    now = now or time.time()
    loc = dt.datetime.fromtimestamp(now + kyiv_offset(now) * 3600, dt.timezone.utc)
    if loc.hour >= 9:
        loc += dt.timedelta(days=1)
    return loc.strftime("%Y-%m-%d")


def last_finished(now: float | None = None) -> str:
    y, m, d = map(int, current_day(now).split("-"))
    return (dt.date(y, m, d) - dt.timedelta(days=1)).strftime("%Y-%m-%d")


async def build(day: str, brain, feed, parser, make_tracker, ctx_dicts) -> dict:
    t0, t1 = window(day)
    rows = list(brain.db.execute("SELECT t, src, link, kind, type, text FROM msg WHERE t >= ? AND t < ? ORDER BY t", (t0 - 1800, t1)))
    from .parser import CHANNEL_CITY
    # офіційний підсумок ранку від Повітряних сил: «станом на 07:30 … збито/подавлено N»
    official = None
    for ts_, text_ in brain.db.execute("SELECT t, text FROM msg WHERE t >= ? AND t < ? AND text LIKE '%подавлено%' ORDER BY t", (t1 - 4 * 3600, t1 + 4 * 3600)):
        m_ = SHOT.search(text_ or "")
        if m_:
            official = {"shot": int(m_.group(1)), "text": text_[:300], "t": int(ts_)}
    shadow = make_tracker()
    saved = [dict(c) for c in ctx_dicts]  # контекст живого моніторингу не чіпаємо
    traj: dict[str, dict] = {}
    booms: dict[str, dict] = {}
    seen_links: set = set()
    nxt = t0
    t_yield = time.monotonic()

    def sample(ts: float) -> None:
        snap = shadow.snapshot(ts)
        for tr in snap["tracks"]:
            if tr["status"] != "active":
                continue
            k = f"{tr['id']}@{int(tr['first'])}"
            e = traj.setdefault(k, {"type": tr["type"], "count": tr["count"] or 1, "pts": [], "obs": {}, "launch": None, "next": None})
            for q in tr.get("trail") or []:  # справжні фіксації каналів — основа маршруту (без «зигзагів» оцінки)
                e["obs"][int(q[2])] = [round(q[0], 4), round(q[1], 4), int(q[2])]
            e["count"] = max(e["count"], tr["count"] or 1)
            if tr.get("launch") and not tr["launch"].get("est"):
                e["launch"] = tr["launch"]["site"]
            e["next"] = tr["next"] or e["next"]
            p = [round(tr["lon"], 4), round(tr["lat"], 4), int(ts)]
            if not e["pts"] or abs(e["pts"][-1][0] - p[0]) + abs(e["pts"][-1][1] - p[1]) > 0.004:
                e["pts"].append(p)
    try:
        for ts, src, link, kind, typ, text in rows:
            while nxt <= ts and nxt < t1:
                if nxt >= t0:
                    sample(nxt)
                nxt += 60
            if kind == "filtered" and ts >= t0 and text and is_impact(text.lower()):
                o = parser.parse(text, src)
                pl = [r.place for r in o.places[:2]]
                if not pl and src in CHANNEL_CITY:  # «Вибух» у міському каналі — це його місто
                    ids = parser.gaz.lookup(CHANNEL_CITY[src])
                    if ids:
                        pl = [max((parser.gaz.places[i] for i in ids), key=lambda q: q.pop)]
                for p in pl:
                    if not (44 <= p.lat <= 52.5 and 22 <= p.lon <= 40.3):
                        continue
                    b = booms.setdefault(p.name, {"n": p.name, "lat": p.lat, "lon": p.lon, "c": 0, "t": int(ts), "last": 0})
                    if ts - b["last"] > 120:  # серія повідомлень про той самий вибух — один епізод
                        b["c"] += 1
                    b["last"] = ts
            if link and (link, text) in seen_links:
                continue
            seen_links.add((link, text))
            feed(shadow, text, src, ts, link, False, typ if kind in ("track", "zone") else None)
            if time.monotonic() - t_yield > 0.02:
                await asyncio.sleep(0.005)
                t_yield = time.monotonic()
        while nxt < t1:
            sample(nxt)
            nxt += 60
            if nxt > time.time():
                break
    finally:
        for live, old in zip(ctx_dicts, saved):
            live.clear()
            live.update(old)
    launches = shadow.launches.snapshot(t1 if t1 < time.time() else time.time())
    tracks = []
    for k, v in traj.items():
        ob = [v["obs"][t] for t in sorted(v["obs"])]
        if ob and v["pts"]:
            last = v["pts"][-1]  # куди ціль летіла після останньої фіксації (оцінка до зникнення)
            if last[2] > ob[-1][2] and abs(last[0] - ob[-1][0]) + abs(last[1] - ob[-1][1]) > 0.02:
                ob.append(last)
        pts = ob if len(ob) >= 2 else v["pts"]
        if len(pts) >= 2:
            tracks.append({"id": k, "type": v["type"], "count": v["count"], "launch": v["launch"], "next": v["next"], "pts": pts})
    tracks = stitch(tracks)
    by_type: dict[str, int] = {}
    for tr in tracks:
        by_type[tr["type"]] = by_type.get(tr["type"], 0) + (tr["count"] or 1)
    sites: dict[str, dict] = {}
    for L in launches:
        if not (t0 <= L["t"] < t1):
            continue
        s = sites.setdefault(L["site"], {"n": L["site"], "lat": L["lat"], "lon": L["lon"], "types": {}, "c": 0})
        s["types"][L["type"] or "?"] = s["types"].get(L["type"] or "?", 0) + (L["count"] or 1)
        s["c"] += L["count"] or 1
    # точки вибухів: лише ті, що підтверджені ≥1 джерелом і не збіглися з «пусками»
    bl = [{"n": b["n"], "lat": b["lat"], "lon": b["lon"], "c": b["c"], "t": b["t"]} for b in booms.values()]
    return {"v": VER, "day": day, "t0": t0, "t1": t1, "final": time.time() > t1 + 4 * 3600 or (t1 <= time.time() and official is not None), "built": int(time.time()), "msgs": len(rows),
            "tracks": tracks, "by_type": by_type, "official": official, "sites": list(sites.values()), "booms": sorted(bl, key=lambda b: -b["c"])}


SPEED = {"shahed": 170, "jet": 450, "molniya": 120, "cruise": 800, "ballistic": 2000, "kab": 400, "geran5": 550, "banderol": 700, "rszv": 1500, "fpv": 80, "fpvf": 60, "recon": 110}


def stitch(tracks: list[dict]) -> list[dict]:
    """Монітори ведуть ціль шматками (кожен канал — свою ділянку). Склеюємо шматки одного типу в маршрут, якщо
    наступний починається там, куди міг долетіти попередній, і напрямок не ламається різко."""
    import math
    from .geo import bearing, dist_km, to_xy
    xy = lambda p: to_xy(p[1], p[0])
    ts = sorted(tracks, key=lambda t: t["pts"][0][2])
    nxt: dict[int, int] = {}
    taken: set[int] = set()
    ends = sorted(range(len(ts)), key=lambda i: ts[i]["pts"][-1][2])
    for j, b in enumerate(ts):
        sb, pb = b["pts"][0][2], xy(b["pts"][0])
        hb = bearing(pb, xy(b["pts"][1])) if len(b["pts"]) > 1 else None
        best, bi = 1e9, None
        for i in ends:
            if i == j or i in nxt:
                continue
            a = ts[i]
            ea = a["pts"][-1][2]
            if a["type"] != b["type"] or not (sb - 1800 <= ea <= sb + 120):
                continue
            pa = xy(a["pts"][-1])
            d = dist_km(pa, pb)
            if d > min(130, SPEED.get(a["type"], 200) * max(0, sb - ea) / 3600 * 1.4 + 35):
                continue
            ha = bearing(xy(a["pts"][-2]), pa) if len(a["pts"]) > 1 else None
            turn = 0.0
            if ha is not None and d > 3:
                turn = abs((bearing(pa, pb) - ha + 540) % 360 - 180)
                if turn > 75:
                    continue
            if ha is not None and hb is not None and abs((hb - ha + 540) % 360 - 180) > 100:
                continue
            cost = d + turn * 0.3
            if cost < best:
                best, bi = cost, i
        if bi is not None and j not in taken:
            nxt[bi] = j
            taken.add(j)
    out = []
    for i, t in enumerate(ts):
        if i in taken:
            continue
        chain, k = dict(t), i
        chain["pts"] = list(t["pts"])
        while k in nxt:
            k = nxt[k]
            chain["pts"] += ts[k]["pts"]
            chain["count"] = max(chain["count"] or 1, ts[k]["count"] or 1)
            chain["launch"] = chain["launch"] or ts[k]["launch"]
            chain["next"] = ts[k]["next"] or chain["next"]
        out.append(chain)
    return out


class Daily:
    def __init__(self, brain, feed, parser, make_tracker, ctx_dicts, push=None) -> None:
        self.args = (brain, feed, parser, make_tracker, ctx_dicts)
        self.push = push
        self.cache: dict[str, dict] = {}
        self.ready: str | None = None
        self.crawling: set[str] = set()
        self.lock = asyncio.Lock()
        OUT.mkdir(parents=True, exist_ok=True)

    async def get(self, day: str) -> dict:
        f = OUT / f"{day}.json"
        c = self.cache.get(day)
        if c and c.get("v") == VER and ((c["final"] and (c.get("crawl") or day in self.crawling)) or time.time() - c["built"] < 300):
            c["crawling"] = day in self.crawling
            return c
        if f.exists():
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("v") == VER and d.get("crawl"):
                self.cache[day] = d
                return d
        async with self.lock:
            d = await build(day, *self.args)
        old = self.cache.get(day)
        if old and old.get("crawl"):  # уже зібрані вибухи з повної історії каналів
            d["booms"], d["crawl"] = old["booms"], old["crawl"]
        self.cache[day] = d
        if d["final"] and d.get("crawl"):
            f.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        if not d.get("crawl") and day not in self.crawling:
            self.crawling.add(day)
            asyncio.create_task(self._crawl(day))
        d["crawling"] = day in self.crawling
        return d

    async def _crawl(self, day: str) -> None:
        try:
            t0, t1 = window(day)
            got = await crawl_impacts(t0, min(t1, time.time()), self.args[2])
            d = self.cache.get(day)
            if d is not None:
                merged = {b["n"]: b for b in d.get("booms", [])}
                for b in got:  # повна історія точніша за живий журнал
                    m = merged.get(b["n"])
                    merged[b["n"]] = b if not m or b["c"] >= m["c"] else m
                d["booms"] = sorted(merged.values(), key=lambda b: -b["c"])
                d["crawl"] = int(time.time())
                d["crawling"] = False
                if d["final"]:
                    (OUT / f"{day}.json").write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                log.info("мапа доби %s: вибухи з історії каналів — %d місць", day, len(got))
        except Exception:  # noqa: BLE001
            log.exception("impacts crawl")
        finally:
            self.crawling.discard(day)

    async def run(self) -> None:
        """Щоранку о 09:00 (Київ) — збирає мапу минулої доби й сповіщає застосунки."""
        await asyncio.sleep(60)
        while True:
            day = last_finished()
            try:
                f = OUT / f"{day}.json"
                if not f.exists() or json.loads(f.read_text(encoding="utf-8")).get("v") != VER:
                    d = await self.get(day)
                    for _ in range(90):  # до 15 хв чекаємо, поки зберуться вибухи з історії каналів
                        if not self.crawling:
                            break
                        await asyncio.sleep(10)
                    log.info("мапа доби %s: %d цілей, %d вибухів", day, len(d["tracks"]), len(d["booms"]))
                    hour = (time.time() / 3600 + kyiv_offset(time.time())) % 24
                    if self.push and d["tracks"] and 9 <= hour < 12:  # пуш лише вранці, не вночі після перезапуску
                        n = sum(d["by_type"].values())
                        await self.push.broadcast("Мапа доби готова", f"За добу до 09:00 — {n} цілей. Маршрути, пуски й вибухи на одній мапі.", {"daily": day})
                self.ready = day
            except Exception:  # noqa: BLE001
                log.exception("daily")
            await asyncio.sleep(120)
