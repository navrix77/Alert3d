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
tracker = Tracker(config.SOURCES)
alerts = OfficialAlerts()
webmon = WebMonitor()
clients: set[WebSocket] = set()
started = time.time()


def on_message(text: str, key: str, ts: float, link: str | None = None) -> None:
    """Одне повідомлення каналу може містити кілька цілей — ділимо на сегменти."""
    segs = parser.segments(text)
    msg_type = parser.parse(text, key).type if len(segs) > 1 else None
    useful = 0
    for seg in segs:
        obs = parser.parse(seg, key)
        if obs.type is None and msg_type and obs.places and not obs.close:
            obs.type = msg_type
        if obs.kind in ("track", "zone", "close", "filtered"):
            tracker.ingest(obs, key, ts, link)
            useful += 1
    if not useful:
        tracker.ingest(parser.parse(text, key), key, ts, link)


def state() -> dict:
    snap = tracker.snapshot()
    off = alerts.state()
    levels = dict(snap["levels_tracker"])
    for k, v in off["levels"].items():
        levels[k] = max(levels.get(k, 0), v)
    snap["levels"] = levels
    snap["official"] = off
    snap["sources"] = {k: {"name": s.name, "rel": s.rel, "official": s.official, "url": s.url} for k, s in config.SOURCES.items()}
    snap["health"] = {
        "telegram": bool(config.TG_SESSION) or os.getenv("REPLAY") == "1" or webmon.state()["live"] > 0,
        "channels": webmon.state(),
        "replay": os.getenv("REPLAY") == "1",
        "alerts": off["ok"],
        "uptime": int(time.time() - started),
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
