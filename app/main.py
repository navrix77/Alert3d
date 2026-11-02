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
from .strikes_ua import UaStrikes
from .forecast import forecast as make_forecast
from . import lan_tls, occupied

brain = Brain()
pushsvc = Push()
ru = RuStrikes()
hits = UaStrikes(parser.gaz)
tracker = Tracker(config.SOURCES, brain)
alerts = OfficialAlerts()
alerts.on_threat = lambda ev: on_threat(ev)
webmon = WebMonitor()
clients: set[WebSocket] = set()
started = time.time()


CTX: dict[str, tuple[float, float, float]] = {}
LASTC: dict[str, tuple[float, str, str]] = {}


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
    # «Далее Алексеевка/Сортировка» — продовження тієї самої цілі, про яку канал писав щойно
    cont = bool(re.match(r"^\W*(далее|дальше|далі|дали|потім|затем|потом)\b", text.lower()))
    last = LASTC.get(key)
    trk.prefer = last[2] if cont and last and ts - last[0] < 420 else None
    for seg in segs:
        obs = parser.parse(seg, key, ctx)
        if obs.type is None and msg_type and obs.places and not obs.close and not obs.no_target:
            obs.type = msg_type
        if obs.type is None and obs.places and not obs.close and not obs.no_target and trk.prefer and last:
            obs.type = last[1]
        # ланцюжок «звідки запущено»: пуск / зліт носіїв / напрямок старту
        sites, ltyp, carrier, _s = launch.detect(seg, obs.type or msg_type)
        if sites:
            trk.launches.add(sites, ltyp, obs.count, carrier, key, link, ts, summary)
            useful += 1
            if log:
                brain.log_msg(ts, key, link, "launch", ltyp, obs.count, [{"r": "L", "n": s.name} for s in sites], None, seg)
            if all(p.role == "f" for p in obs.places):  # «пуски з X» без місця в Україні — це не трек
                continue
        if obs.kind in ("track", "zone", "close", "filtered", "avia"):
            obs.raw = seg
            rec = trk.ingest(obs, key, ts, link)
            if rec.get("track") and obs.kind == "track":
                LASTC[key] = (ts, obs.type, rec["track"])
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
    obs.raw = ev["text"]
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
    if time.time() - ts < 300:
        alerts.fast_signal(text, ts)  # швидкий старт/відбій тривоги з ретрансляцій каналів
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


from .daily import Daily, current_day, last_finished  # noqa: E402

from .learner import Learner  # noqa: E402

LEARNER = Learner(tracker, brain)
daily = Daily(brain, feed, parser, lambda: Tracker(config.SOURCES), [CTX, LASTC], pushsvc)
_FC = (0.0, {})
HIST: list[dict] = brain.hist_load(time.time() - 12 * 3600)


def state() -> dict:
    snap = tracker.snapshot()
    off = alerts.state()
    # Заливка регіонів — ЛИШЕ офіційні тривоги. Оцінка трекера йде окремо (levels_tracker) і регіони не фарбує.
    snap["levels"] = dict(off["levels"])
    snap["official"] = off
    # КАБ без тривоги в області не буває: якщо офіційна тривога там знята — зону й авіацію прибираємо
    if off.get("ok") and off.get("alert_obl") is not None:
        ao = set(off["alert_obl"])
        snap["zones"] = [z for z in snap.get("zones", []) if not z.get("obl") or z["obl"] in ao]
        snap["avia"] = [a for a in snap.get("avia", []) if a["obl"] in ao]
    snap["ru"] = ru.state()
    snap["hits"] = hits.state()
    global _FC
    if time.time() - _FC[0] > 20:
        try:
            _FC = (time.time(), make_forecast(snap, tracker.launches.snapshot(snap["now"]), brain, parser.gaz))
        except Exception:  # noqa: BLE001
            log.exception("forecast")
    snap["forecast"] = _FC[1]
    # машина часу: кадр раз на хвилину, 12 годин
    if not HIST or snap["now"] - HIST[-1]["t"] >= 60:
        fr = {"t": int(snap["now"]), "levels": snap.get("levels", {}), "raions": snap["official"].get("raion_levels", {}),
              "tracks": [{"id": t["id"], "type": t["type"], "lat": t["lat"], "lon": t["lon"], "hd": t["hd"], "count": t["count"], "conf": t["conf"], "next": t["next"],
                          "route": t["route"][:3],
                          # що було ВІДОМО в цей момент: докази на ту хвилину
                          "ev": {"pubs": t["ev"]["pubs"], "prim": t["ev"]["prim"], "indep": t["ev"]["indep"], "age": t["ev"]["age"], "contra": t["ev"]["contra"],
                                 "items": [{k: i[k] for k in ("t", "src", "p", "pt", "copy", "dest", "why")} for i in t["ev"]["items"][-8:]]}}
                         for t in snap["tracks"] if t["status"] == "active"]}
        HIST.append(fr)
        brain.hist_add(fr)
        while HIST and snap["now"] - HIST[0]["t"] > 12 * 3600:
            HIST.pop(0)
    snap["sources"] = {k: {"name": s.name, "rel": round(brain.rel(k, s.rel), 2), "prior": s.rel, "official": s.official, "url": s.url} for k, s in config.SOURCES.items()}
    snap["daily"] = daily.ready
    snap["pred_acc"] = brain.pred_acc()
    snap["health"] = {
        "telegram": bool(config.TG_SESSION) or os.getenv("REPLAY") == "1" or webmon.state()["live"] > 0,
        "channels": webmon.state(),
        "replay": os.getenv("REPLAY") == "1",
        "alerts": off["ok"],
        "uptime": int(time.time() - started),
        "version": "2026-11-02.1",
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
    tasks.append(asyncio.create_task(occupied.run()))
    tasks.append(asyncio.create_task(hits.run()))
    if os.getenv("REPLAY") != "1":
        tasks.append(asyncio.create_task(daily.run()))
    if os.getenv("PERSIST_DIR"):
        async def _snap():
            while True:
                await asyncio.sleep(600)
                await asyncio.to_thread(brain.snapshot)
        tasks.append(asyncio.create_task(_snap()))
    tasks.append(asyncio.create_task(LEARNER.run()))
    if os.getenv("LAN_TLS", "1") == "1":
        tasks.append(asyncio.create_task(lan_tls.run()))
    if os.getenv("REPLAY") != "1":
        tasks.append(asyncio.create_task(telegram_src.run(on_message) if config.TG_SESSION else webmon.run(on_message)))
        tasks.append(asyncio.create_task(learn_history()))
    log.info("Тривога запущена: %d каналів", len(config.CHANNELS))
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="NAVRYX SKY", lifespan=lifespan)
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)  # geojson і скрипти стискаються в 3-5 разів


@app.get("/api/audit")
def api_audit():
    """Самоаналіз: аномалії розбору й треків + точність навченого прогнозу."""
    from .audit import AUDIT
    st = AUDIT.state()
    st["pred_acc"] = brain.pred_acc() if hasattr(brain, "pred_acc") else None
    st["learn"] = LEARNER.state()
    return st


@app.get("/api/state")
def api_state():
    return JSONResponse(state())


@app.get("/api/config")
def api_config():
    return {"vectorStyle": config.MAP_STYLE_VECTOR, "maptilerKey": config.MAPTILER_KEY or None, "gtilesKey": config.GOOGLE_TILES_KEY or None}


@app.post("/api/push/register")
async def push_register(body: dict):
    ok = pushsvc.register(str(body.get("token", "")), float(body.get("lon", 0)), float(body.get("lat", 0)))
    return JSONResponse({"ok": ok}, status_code=200 if ok else 400)


@app.post("/api/push/unregister")
async def push_unregister(body: dict):
    pushsvc.unregister(str(body.get("token", "")))
    return {"ok": True}


@app.get("/api/daily")
async def api_daily(d: str | None = None):
    """Мапа доби 09:00→09:00. d — дата ранку, коли доба закінчилась; без d — остання завершена."""
    import re as _re
    day = d if d and _re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) else last_finished()
    if day > current_day():
        return JSONResponse({"error": "доба ще не почалась"}, status_code=404)
    return JSONResponse(await daily.get(day))


@app.get("/api/history")
def api_history():
    return JSONResponse({"frames": HIST})


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
    # спершу домашня Wi‑Fi (192.168.*, 10.*), віртуальні адаптери (172.16–31.*: WSL/Hyper‑V) — в кінці
    rank = lambda i: 0 if i.startswith("192.168.") else 1 if i.startswith("10.") else 2
    ips = sorted((i for i in ips if not i.startswith("127.") and not i.startswith("169.254.")), key=lambda i: (rank(i), i))
    return {"urls": [f"http://{i}:8090" for i in ips], "secure": [f"https://{i}:{lan_tls.PORT}" for i in ips] if (lan_tls.DIR / "tryvoga.crt").exists() else []}


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
    allowed = {"oblasts.geojson", "raions.geojson", "occupied.geojson", "hromadas.geojson", "outside.geojson"}
    if name not in allowed or not (ROOT / "data" / name).exists():
        return JSONResponse({"type": "FeatureCollection", "features": []} if name == "occupied.geojson" else {"error": "not found"},
                            status_code=200 if name == "occupied.geojson" else 404)
    return FileResponse(ROOT / "data" / name, media_type="application/geo+json")


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
