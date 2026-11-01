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
OUT = Path(__file__).resolve().parent.parent / "data" / "daily"
BOOM = re.compile(r"вибух|взрыв|прил[іеё]т|влучан|попадан|детонац|пожеж|ураж")
NOT_BOOM = re.compile(r"збит|сбит|мінус|минус|ппо працю|пво работ|роботу ппо|роботою ппо|роботою пво|не фіксу|відбій|наслідки .* \d+ жовтня|історі")
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
            e = traj.setdefault(k, {"type": tr["type"], "count": tr["count"] or 1, "pts": [], "launch": None, "next": None})
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
            if kind == "filtered" and ts >= t0 and text and BOOM.search(text.lower()) and not NOT_BOOM.search(text.lower()):
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
            feed(shadow, text, src, ts, link, False)
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
    tracks = [dict(id=k, **v) for k, v in traj.items() if len(v["pts"]) >= 2 or v["launch"]]
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
    return {"day": day, "t0": t0, "t1": t1, "final": time.time() > t1 + 4 * 3600 or (t1 <= time.time() and official is not None), "built": int(time.time()), "msgs": len(rows),
            "tracks": tracks, "by_type": by_type, "official": official, "sites": list(sites.values()), "booms": sorted(bl, key=lambda b: -b["c"])}


class Daily:
    def __init__(self, brain, feed, parser, make_tracker, ctx_dicts, push=None) -> None:
        self.args = (brain, feed, parser, make_tracker, ctx_dicts)
        self.push = push
        self.cache: dict[str, dict] = {}
        self.ready: str | None = None
        self.lock = asyncio.Lock()
        OUT.mkdir(parents=True, exist_ok=True)

    async def get(self, day: str) -> dict:
        f = OUT / f"{day}.json"
        if day in self.cache and (self.cache[day]["final"] or time.time() - self.cache[day]["built"] < 300):
            return self.cache[day]
        if f.exists():
            d = json.loads(f.read_text(encoding="utf-8"))
            self.cache[day] = d
            return d
        async with self.lock:
            d = await build(day, *self.args)
        self.cache[day] = d
        if d["final"]:
            f.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return d

    async def run(self) -> None:
        """Щоранку о 09:00 (Київ) — збирає мапу минулої доби й сповіщає застосунки."""
        await asyncio.sleep(60)
        while True:
            day = last_finished()
            try:
                if not (OUT / f"{day}.json").exists():
                    d = await self.get(day)
                    log.info("мапа доби %s: %d цілей, %d вибухів", day, len(d["tracks"]), len(d["booms"]))
                    if self.push and d["tracks"]:
                        n = sum(d["by_type"].values())
                        await self.push.broadcast("Мапа доби готова", f"За добу до 09:00 — {n} цілей. Маршрути, пуски й вибухи на одній мапі.", {"daily": day})
                self.ready = day
            except Exception:  # noqa: BLE001
                log.exception("daily")
            await asyncio.sleep(120)
