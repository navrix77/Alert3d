"""«Тривога»: API + WebSocket + статика PWA. Один контейнер для Cloud Run (min-instances=1)."""
from __future__ import annotations

import asyncio
import json
import re
import os
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, replay, telegram_src
from .tg_web import WebMonitor
from .alerts import OfficialAlerts
from .parser import Parser
from .tracker import Tracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("tryvoga")
ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

parser = Parser()
from . import launch
from .brain import Brain
from .push import Push
from .ru_strikes import RuStrikes

brain = Brain()
pushsvc = Push()
ru = RuStrikes()
tracker = Tracker(config.SOURCES, brain)
alerts = OfficialAlerts()
alerts.on_threat = lambda ev: on_threat(ev)
webmon = WebMonitor()
clients: set[WebSocket] = set()
started = time.time()


CTX: dict[str, tuple[float, float, float]] = {}


def feed(trk: Tracker, text: str, key: str, ts: float, link: str | None, log: bool) -> None:
    """Одне повідомлення каналу може містити кілька цілей — ділимо на сегменти й кожен веде в трекер."""
    segs = parser.segments(text)
    # контекст для одноіменних сіл: усі пункти повідомлення разом + що канал називав останні 30 хв
    prev = CTX.get(key)
    pctx = (prev[1], prev[2]) if prev and 0 <= ts - prev[0] < 1800 else None
    whole = parser.parse(text, key, pctx)
    ctx = pctx
    if whole.places:
        la = sum(r.place.lat for r in whole.places) / len(whole.places)
        lo = sum(r.place.lon for r in whole.places) / len(whole.places)
        ctx = (la, lo)
        CTX[key] = (ts, la, lo)
    msg_type = whole.type if len(segs) > 1 else None
    summary = bool(launch.SUMMARY_RX.search(text.lower()))
    useful = 0
    trk.exclude = set()
    for seg in segs:
        obs = parser.parse(seg, key, ctx)
        if obs.type is None and msg_type and obs.places and not obs.close:
            obs.type = msg_type
        # ланцюжок «звідки запущено»: пуск / зліт носіїв / напрямок старту
        sites, ltyp, carrier, _s = launch.detect(seg, obs.type or msg_type)
        if sites:
            trk.launches.add(sites, ltyp, obs.count, carrier, key, link, ts, summary)
            useful += 1
            if log:
                brain.log_msg(ts, key, link, "launch", ltyp, obs.count, [{"r": "L", "n": s.name} for s in sites], None, seg)
            if all(p.role == "f" for p in obs.places):  # «пуски з X» без місця в Україні — це не трек
                continue
        if obs.kind in ("track", "zone", "close", "filtered"):
            rec = trk.ingest(obs, key, ts, link)
            if len(segs) > 1 and rec.get("track"):
                trk.exclude.add(rec["track"])
            useful += 1
            if log:
                brain.log_msg(ts, key, link, obs.kind, obs.type, obs.count, rec.get("places"), rec.get("track"), seg)
    trk.exclude = set()
    if not useful:
        trk.ingest(parser.parse(text, key), key, ts, link)


def on_threat(ev: dict) -> None:
    """Офіційна фіксація з alerts.in.ua: місце (село/місто/район) + тип + курс."""
    from .parser import Observation, PlaceRef
    name = re.sub(r"^(с\.|смт|м\.|сел\.)\s*", "", ev["place"]).strip()
    place = None
    if name.endswith("район"):
        place = raion_centroid(name.replace(" район", "").strip())
    else:
        ids = parser.gaz.lookup(name)
        if ids:
            ctx = CTX.get("AIU")
            P = [parser.gaz.places[i] for i in ids]
            place = max(P, key=lambda p: p.pop) if len(P) == 1 or not ctx else min(P, key=lambda p: (p.lat - ctx[1]) ** 2 + (p.lon - ctx[2]) ** 2)
    if not place:
        return
    obs = Observation(type=ev["type"], count=ev["count"], places=[PlaceRef("p", place)], course=ev["heading"])
    tracker.ingest(obs, "AIU", ev["t"], "https://alerts.in.ua")
    brain.log_msg(ev["t"], "AIU", None, obs.kind, obs.type, obs.count, [{"r": "p", "n": place.name}], None, ev["text"])


_RC: dict = {}


def raion_centroid(n: str):
    from .geo import Place
    if not _RC:
        d = json.loads((Path(__file__).resolve().parent.parent / "data" / "raions.geojson").read_text(encoding="utf-8"))
        for f in d["features"]:
            g = f["geometry"]
            pts = [p for poly in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]) for p in poly[0]]
            _RC[f["properties"]["n"]] = Place(f["properties"]["n"] + " р-н", sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts), "R", 1000)
    ap = lambda x: x.replace("’", "'").replace("ʼ", "'")
    for k, v in _RC.items():
        if ap(k) == ap(n):
            return v
    return None


def on_message(text: str, key: str, ts: float, link: str | None = None) -> None:
    # повідомлення, яке вже бачили до перезапуску, відновлює трек, але не вчить модель вдруге
    again = brain.seen(link)
    tracker.learn = not again
    feed(tracker, text, key, ts, link, log=not again)
    tracker.learn = True


async def learn_history() -> None:
    """«Пилосос» по історії: тиждень постів головних каналів проганяється через тіньовий трекер,
    щоб вивчити реальні маршрути цілей ще до першої живої тривоги."""
    if os.getenv("REPLAY") == "1" or os.getenv("LEARN_HISTORY", "1") != "1":
        return
    await asyncio.sleep(25)  # спершу — живий моніторинг
    try:
        posts = await webmon.crawl_history(days=int(os.getenv("LEARN_DAYS", "7")))
    except Exception as e:  # noqa: BLE001
        log.warning("history crawl failed: %s", e)
        return
    shadow = Tracker(config.SOURCES, brain)
    n = 0
    t_yield = time.monotonic()
    for ts, text, key, link in sorted(posts):
        if brain.seen(link):
            continue
        feed(shadow, text, key, ts, link, log=True)
        n += 1
        if n % 25 == 0:
            shadow.snapshot(ts)  # прибирає старі треки й оновлює довіру
        # навчання у фоні НЕ має гальмувати живий моніторинг: віддаємо цикл подій щонайменше кожні 20 мс
        if time.monotonic() - t_yield > 0.02:
            await asyncio.sleep(0.01)
            t_yield = time.monotonic()
    brain.flush()
    log.info("історія: вивчено %d постів; модель маршрутів: %s", n, brain.stats())


def state() -> dict:
    snap = tracker.snapshot()
    off = alerts.state()
    # Заливка регіонів — ЛИШЕ офіційні тривоги. Оцінка трекера йде окремо (levels_tracker) і регіони не фарбує.
    snap["levels"] = dict(off["levels"])
    snap["official"] = off
    snap["ru"] = ru.state()
    snap["sources"] = {k: {"name": s.name, "rel": round(brain.rel(k, s.rel), 2), "prior": s.rel, "official": s.official, "url": s.url} for k, s in config.SOURCES.items()}
    snap["health"] = {
        "telegram": bool(config.TG_SESSION) or os.getenv("REPLAY") == "1" or webmon.state()["live"] > 0,
        "channels": webmon.state(),
        "replay": os.getenv("REPLAY") == "1",
        "alerts": off["ok"],
        "uptime": int(time.time() - started),
        "version": "2026-11-01.10",
        "push_subs": pushsvc.count(),
        "brain": brain.stats(),
    }
    return snap


async def pusher() -> None:
    while True:
        await asyncio.sleep(config.PUSH_SEC)
        if not clients:
            continue
        msg = json.dumps(state(), ensure_ascii=False)
        dead = []
        for ws in list(clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            clients.discard(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [asyncio.create_task(pusher()), asyncio.create_task(alerts.run()), asyncio.create_task(replay.run(tracker))]
    tasks.append(asyncio.create_task(pushsvc.run(state)))
    tasks.append(asyncio.create_task(ru.run()))
    if os.getenv("REPLAY") != "1":
        tasks.append(asyncio.create_task(telegram_src.run(on_message) if config.TG_SESSION else webmon.run(on_message)))
        tasks.append(asyncio.create_task(learn_history()))
    log.info("Тривога запущена: %d каналів", len(config.CHANNELS))
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Тривога", lifespan=lifespan)


@app.get("/api/state")
def api_state():
    return JSONResponse(state())


@app.get("/api/config")
def api_config():
    return {"vectorStyle": config.MAP_STYLE_VECTOR, "maptilerKey": config.MAPTILER_KEY or None}


@app.post("/api/push/register")
async def push_register(body: dict):
    ok = pushsvc.register(str(body.get("token", "")), float(body.get("lon", 0)), float(body.get("lat", 0)))
    return JSONResponse({"ok": ok}, status_code=200 if ok else 400)


@app.post("/api/push/unregister")
async def push_unregister(body: dict):
    pushsvc.unregister(str(body.get("token", "")))
    return {"ok": True}


@app.get("/api/lan")
def api_lan():
    """Адреси цього комп'ютера в локальній мережі — щоб відкрити «Тривогу» на телефоні (QR у налаштуваннях)."""
    import socket
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:  # noqa: BLE001
        pass
    ips = sorted(i for i in ips if not i.startswith("127.") and not i.startswith("169.254."))
    return {"urls": [f"http://{i}:8090" for i in ips]}


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        await ws.send_text(json.dumps(state(), ensure_ascii=False))
        while True:
            await ws.receive_text()  # ping від клієнта
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)


@app.get("/data/{name}")
def data_file(name: str):
    allowed = {"oblasts.geojson", "raions.geojson"}
    if name not in allowed:
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(ROOT / "data" / name, media_type="application/geo+json")


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
