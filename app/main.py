"""«Тривога»: API + WebSocket + статика PWA. Один контейнер для Cloud Run (min-instances=1)."""
from __future__ import annotations

import asyncio
import json
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

brain = Brain()
tracker = Tracker(config.SOURCES, brain)
alerts = OfficialAlerts()
webmon = WebMonitor()
clients: set[WebSocket] = set()
started = time.time()


def feed(trk: Tracker, text: str, key: str, ts: float, link: str | None, log: bool) -> None:
    """Одне повідомлення каналу може містити кілька цілей — ділимо на сегменти й кожен веде в трекер."""
    segs = parser.segments(text)
    whole = parser.parse(text, key)
    msg_type = whole.type if len(segs) > 1 else None
    summary = bool(launch.SUMMARY_RX.search(text.lower()))
    useful = 0
    for seg in segs:
        obs = parser.parse(seg, key)
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
            useful += 1
            if log:
                brain.log_msg(ts, key, link, obs.kind, obs.type, obs.count, rec.get("places"), rec.get("track"), seg)
    if not useful:
        trk.ingest(parser.parse(text, key), key, ts, link)


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
    for ts, text, key, link in sorted(posts):
        if brain.seen(link):
            continue
        feed(shadow, text, key, ts, link, log=True)
        shadow.snapshot(ts)  # прибирає старі треки й оновлює довіру
        n += 1
        if n % 200 == 0:
            await asyncio.sleep(0)
    brain.flush()
    log.info("історія: вивчено %d постів; модель маршрутів: %s", n, brain.stats())


def state() -> dict:
    snap = tracker.snapshot()
    off = alerts.state()
    # Заливка регіонів — ЛИШЕ офіційні тривоги. Оцінка трекера йде окремо (levels_tracker) і регіони не фарбує.
    snap["levels"] = dict(off["levels"])
    snap["official"] = off
    snap["sources"] = {k: {"name": s.name, "rel": round(brain.rel(k, s.rel), 2), "prior": s.rel, "official": s.official, "url": s.url} for k, s in config.SOURCES.items()}
    snap["health"] = {
        "telegram": bool(config.TG_SESSION) or os.getenv("REPLAY") == "1" or webmon.state()["live"] > 0,
        "channels": webmon.state(),
        "replay": os.getenv("REPLAY") == "1",
        "alerts": off["ok"],
        "uptime": int(time.time() - started),
        "version": "2026-11-01.6",
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
