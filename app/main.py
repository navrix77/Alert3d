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

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, replay, telegram_src
from . import parser as parser_mod
from .tg_web import WebMonitor
from .alerts import OfficialAlerts
from .parser import Parser
from .tracker import TYPES, Tracker

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
from .llm import LLM

brain = Brain()
pushsvc = Push()
ru = RuStrikes()
hits = UaStrikes(parser.gaz)
tracker = Tracker(config.SOURCES, brain, audit=True)
alerts = OfficialAlerts()
alerts.on_threat = lambda ev: on_threat(ev)
webmon = WebMonitor()
clients: set[WebSocket] = set()
started = time.time()


CTX: dict[str, tuple[float, float, float]] = {}
LASTC: dict[str, tuple[float, str, str]] = {}


FRESH: dict = {"any": 0.0, "obl": {}}  # коли востаннє були повідомлення про цілі: загалом і по кожній області


def _fresh(obs, ts: float) -> None:
    from .geo import oblasts
    FRESH["any"] = max(FRESH["any"], ts)
    O = oblasts()
    for r in obs.places:
        o = O.of(r.place.lon, r.place.lat)
        if o:
            FRESH["obl"][o] = max(FRESH["obl"].get(o, 0), ts)


def feed(trk: Tracker, text: str, key: str, ts: float, link: str | None, log: bool, typ_hint: str | None = None) -> None:
    """Одне повідомлення каналу може містити кілька цілей, ділимо на сегменти й кожен веде в трекер."""
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
    if len(segs) > 1 and parser_mod.AFTERMATH.search(text.lower()):
        msg_type = None  # підсумок/наслідки — тип із заголовка не переносимо на перелічені пункти
        segs = [sg for sg in segs if not parser_mod.AFTERMATH.search(sg.lower())]
    if typ_hint and not msg_type:
        msg_type = typ_hint  # повтор із журналу: тип був у заголовку початкового повідомлення
    summary = bool(launch.SUMMARY_RX.search(text.lower()))
    useful = 0
    trk.exclude = set()
    # «Далее Алексеевка/Сортировка» — продовження тієї самої цілі, про яку канал писав щойно
    cont = bool(re.match(r"^\W*(далее|дальше|далі|дали|потім|затем|потом)\b", text.lower()))
    last = LASTC.get(key)
    trk.prefer = last[2] if cont and last and ts - last[0] < 420 else None
    for seg in segs:
        obs = parser.parse(seg, key, ctx)
        if obs.type and not obs.close and parser_mod.is_junk(seg):
            obs.type, obs.no_target = None, True  # довгий текст без ознак руху: новина, підсумок, реклама
        if obs.type is None and msg_type and obs.places and not obs.close and not obs.no_target and (len(segs) > 1 or typ_hint):
            obs.type = msg_type
        if obs.type is None and obs.places and not obs.close and not obs.no_target and trk.prefer and last:
            obs.type = last[1]
        # «Заїченці курс Вʼязівок» без типу: канал щойно (≤20 хв) писав про цілі певного типу — це продовження
        # (ppopoltavanightfighters пише тип лише в першому пості хвилі)
        if obs.type is None and obs.places and not obs.close and not obs.no_target and last and ts - last[0] < 1200 and re.search(r"курс|→|вектор", seg.lower()):
            obs.type = last[1]
        # ланцюжок «звідки запущено»: пуск / зліт носіїв / напрямок старту
        sites, ltyp, carrier, _s = launch.detect(seg, obs.type or msg_type)
        if sites:
            trk.launches.add(sites, ltyp, obs.count, carrier, key, link, ts, summary, seg)
            useful += 1
            if log:
                brain.log_msg(ts, key, link, "launch", ltyp, obs.count, [{"r": "L", "n": s.name} for s in sites], None, seg)
            if all(p.role == "f" for p in obs.places):  # «пуски з X» без місця в Україні — це не трек
                continue
        if obs.places and obs.type and time.time() - ts < 3600:
            _fresh(obs, ts)
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
        o_ = parser.parse(text, key)
        o_.raw = text
        trk.ingest(o_, key, ts, link)


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


STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "tracker_state.pkl"
FUSION_FILE = Path(__file__).resolve().parent.parent / "data" / "fusion.json"
SELFCHECK_FILE = Path(__file__).resolve().parent.parent / "data" / "selfcheck.json"
try:  # ключі, передані власником через GitHub (зашифровано для цього сервера) — до створення LLM
    from . import secrets_sync
    secrets_sync.apply_pending()
except Exception:  # noqa: BLE001
    logging.getLogger("secrets").exception("apply_pending")
LLMX = LLM()
AIX = None  # зв'язка моделі з SKY (app/ai_glue.py), створюється на старті
RESTORED: dict[str, float] = {}  # посилання на пости, вже враховані у відновленому стані трекера


def on_message(text: str, key: str, ts: float, link: str | None = None) -> None:
    if link and link in RESTORED:
        return  # пост уже в стані, відновленому після перезапуску: вдруге не додаємо (інакше дублі спостережень)
    if time.time() - ts < 300:
        alerts.fast_signal(text, ts)  # швидкий старт/відбій тривоги з ретрансляцій каналів
    # повідомлення, яке вже бачили до перезапуску, відновлює трек, але не вчить модель вдруге
    again = brain.seen(link)
    tracker.learn = not again
    feed(tracker, text, key, ts, link, log=not again)
    tracker.learn = True
    if not again:
        try:
            LLMX.consider(parser, text, key, ts, link)  # сумнівні — моделі (поки лише в журнал, мапу не змінює)
            img = webmon.photo(link) if link else None
            if img and AIX:
                AIX.vision(text, key, ts, link, img)  # мапа/схема в пості — модель із зором (тінь)
        except Exception:  # noqa: BLE001
            log.exception("llm")


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
from .discover import Discover, apply as _apply_auto, load as _load_auto  # noqa: E402

DISCOVER = Discover(parser)
_apply_auto(_load_auto())  # джерела, знайдені раніше, — одразу в моніторинг
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
        if "Київ" in ao or "Київська" in ao:
            ao |= {"Київ", "Київська"}
        snap["zones"] = [z for z in snap.get("zones", []) if not z.get("obl") or z["obl"] in ao]
        snap["avia"] = [a for a in snap.get("avia", []) if a["obl"] in ao]
    snap["ru"] = ru.state()
    snap["hits"] = hits.state()
    global _FC
    if time.time() - _FC[0] > 120:  # панель прогнозу прихована — рахуємо рідко
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
                                 "items": [{k: i[k] for k in ("t", "src", "p", "pt", "copy", "dest", "why")}
                                           for i in ((tracker.track_evidence(t["id"], snap["now"]) or {}).get("items") or [])[-8:]]}}
                         for t in snap["tracks"] if t["status"] == "active"]}
        HIST.append(fr)
        brain.hist_add(fr)
        while HIST and snap["now"] - HIST[0]["t"] > 12 * 3600:
            HIST.pop(0)
    _dt = brain.dir_table(10)
    snap["sources"] = {k: {"name": s.name, "rel": round(brain.rel(k, s.rel), 2), "prior": s.rel, "official": s.official, "url": s.url,
                           **({"dir": _dt[k]} if k in _dt else {})} for k, s in config.SOURCES.items()}
    snap["daily"] = daily.ready
    snap["pred_acc"] = brain.pred_acc()
    _ws = webmon.state()
    snap["fresh"] = {"any": int(FRESH["any"]), "obl": {k: int(v) for k, v in FRESH["obl"].items() if time.time() - v < 6 * 3600},
                     "alerts": int(off.get("updated") or 0), "alerts_ok": bool(off.get("ok")),
                     "live": _ws.get("live", 0), "channels": _ws.get("channels", 0)}
    snap["health"] = {
        "telegram": bool(config.TG_SESSION) or os.getenv("REPLAY") == "1" or webmon.state()["live"] > 0,
        "channels": webmon.state(),
        "replay": os.getenv("REPLAY") == "1",
        "alerts": off["ok"],
        "uptime": int(time.time() - started),
        "version": "2026-11-04.1",
        "push_subs": pushsvc.count(),
        "brain": brain.stats(),
    }
    return snap


HIDDEN: set = set()  # клієнти, чия вкладка/застосунок у фоні — їм рідше


async def pusher() -> None:
    """Повний стан, лише коли щось змінилось (нове повідомлення каналу чи офіційна тривога) або раз на 10 с як «пульс»;
    фоновим вкладкам, раз на 30 с. Мапа між оновленнями сама рухає цілі. Довідник джерел і журнал (≈28 КБ), раз на 30 с.
    Раніше: ~290 КБ кожні 2 с кожному, до ~80 МБ/год на телефон з відкритою мапою."""
    last_sig, last_full, last_sent = None, 0.0, {}
    while True:
        await asyncio.sleep(config.PUSH_SEC)
        if not clients:
            continue
        now = time.time()
        try:
            off = alerts.state()
            sig = (tracker.last_update, json.dumps(off.get("levels"), sort_keys=True), len(tracker.tracks))
        except Exception:  # noqa: BLE001
            sig = None
        due = [ws for ws in list(clients)
               if sig != last_sig or now - last_sent.get(id(ws), 0) >= (30 if ws in HIDDEN else 10)]
        if not due:
            continue
        try:
            snap = state()
        except Exception:  # одна погана ціль не має зупиняти оновлення для всіх
            log.exception("state() failed")
            continue
        full = now - last_full >= 30
        if full:
            last_full = now
        else:
            snap = {k: v for k, v in snap.items() if k not in ("sources", "log")}
        msg = json.dumps(snap, ensure_ascii=False)
        last_sig = sig
        dead = []
        for ws in due:
            try:
                await ws.send_text(msg)
                last_sent[id(ws)] = now
            except Exception:
                dead.append(ws)
        for ws in dead:
            clients.discard(ws)
            HIDDEN.discard(ws)
        if len(last_sent) > 4 * len(clients) + 50:
            alive = {id(w) for w in clients}
            last_sent = {k: v for k, v in last_sent.items() if k in alive}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # журнал пусків живе в пам'яті: після перезапуску відновлюємо пуски за 6 год із журналу повідомлень на диску
    try:
        rows = brain.db.execute("SELECT t, src, link, type, cnt, text FROM msg WHERE kind='launch' AND t > ? ORDER BY t", (time.time() - 6 * 3600,)).fetchall()
        for t_, src_, link_, typ_, cnt_, text_ in rows:
            sites_, ltyp_, car_, _ = launch.detect(text_ or "", typ_)
            if sites_:
                tracker.launches.add(sites_, ltyp_, cnt_, car_, src_, link_, t_, False, text_)
        log.info("відновлено пусків з журналу: %d повідомлень", len(rows))
    except Exception as e:  # noqa: BLE001
        log.warning("відновлення пусків: %s", e)
    # стан трекера з попереднього запуску (якщо йому ≤15 хв): цілі не зникають і не дублюються після оновлення
    try:
        if STATE_FILE.exists() and tracker.load_state(STATE_FILE.read_bytes()):
            since = time.time() - 2 * 3600
            for (lk,) in brain.db.execute("SELECT DISTINCT link FROM msg WHERE t > ? AND t <= ? AND link IS NOT NULL", (since, tracker.restored_at)):
                RESTORED[lk] = 1
            log.info("стан трекера відновлено: %d цілей, %d постів позначено як враховані", len(tracker.tracks), len(RESTORED))
    except Exception as e:  # noqa: BLE001
        log.warning("відновлення стану трекера: %s", e)

    async def _save_state():
        while True:
            await asyncio.sleep(60)
            try:
                raw = tracker.dump_state()  # у потоці подій: трекер не змінюється під час серіалізації
                tmp = STATE_FILE.with_suffix(".tmp")
                await asyncio.to_thread(tmp.write_bytes, raw)
                await asyncio.to_thread(tmp.replace, STATE_FILE)
            except Exception as e:  # noqa: BLE001
                log.warning("збереження стану трекера: %s", e)
    # злиття напрямку: останнє рішення з диска, далі щодня о ~05:30 перевірка на журналі прогнозів
    from . import fusion as _fusion
    try:
        if FUSION_FILE.exists():
            tracker.fusion = json.loads(FUSION_FILE.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("fusion.json: %s", e)

    async def _fusion_daily():
        while True:
            lt = time.localtime()
            wait = ((5 - lt.tm_hour) * 3600 + (30 - lt.tm_min) * 60 - lt.tm_sec) % 86400 or 86400
            await asyncio.sleep(wait)
            try:
                rep = await asyncio.to_thread(_fusion.evaluate, brain.db)
                tracker.fusion = rep
                FUSION_FILE.write_text(json.dumps(rep, ensure_ascii=False), encoding="utf-8")
                log.info("злиття напрямку: %s (%s)", "увімкнено" if rep["on"] else "вимкнено", rep["why"])
            except Exception as e:  # noqa: BLE001
                log.warning("перевірка злиття: %s", e)
    async def _selfcheck_daily():
        """Щоденний самоаналіз на самому сервері (тут журнал): о ~05:40 → data/selfcheck.json, читає рутина через /api/selfcheck."""
        import sys as _sys
        root = Path(__file__).resolve().parent.parent
        first = not SELFCHECK_FILE.exists() or time.time() - SELFCHECK_FILE.stat().st_mtime > 20 * 3600
        while True:
            if first:  # звіту немає або він старий (перший запуск, простій) — робимо одразу, а не чекаємо 05:40
                first = False
                await asyncio.sleep(90)
            else:
                lt = time.localtime()
                await asyncio.sleep(((5 - lt.tm_hour) * 3600 + (40 - lt.tm_min) * 60 - lt.tm_sec) % 86400 or 86400)
            try:
                pr = await asyncio.create_subprocess_exec("nice", "-n", "15", _sys.executable, str(root / "scripts" / "selfcheck.py"),
                                                          str(root / "data" / "brain.sqlite"), "--days", "3", "--out", str(SELFCHECK_FILE),
                                                          cwd=str(root), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
                _o, err = await asyncio.wait_for(pr.communicate(), timeout=1800)
                if pr.returncode:
                    log.warning("selfcheck: код %s %s", pr.returncode, (err or b"")[-300:].decode(errors="ignore"))
            except Exception as e:  # noqa: BLE001
                log.warning("selfcheck: %s", e)
    tasks = [asyncio.create_task(pusher()), asyncio.create_task(_save_state()), asyncio.create_task(_fusion_daily()), asyncio.create_task(_selfcheck_daily()), asyncio.create_task(alerts.run()), asyncio.create_task(replay.run(tracker))]
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
    tasks.append(asyncio.create_task(LLMX.run()))
    global AIX
    from .ai_glue import AI
    AIX = AI(LLMX, parser, tracker, state)
    tasks.append(asyncio.create_task(AIX.merge_watch()))
    tasks.append(asyncio.create_task(AIX.daily(SELFCHECK_FILE)))

    async def _calib_nightly():  # 09:20 щодня: перерахунок калібрування прогнозу за історією знімків (окремий процес)
        root = Path(__file__).resolve().parent.parent
        while True:
            lt = time.localtime()
            await asyncio.sleep(((9 - lt.tm_hour) * 3600 + (20 - lt.tm_min) * 60 - lt.tm_sec) % 86400 or 86400)
            try:
                import sys as _sys2
                pr = await asyncio.create_subprocess_exec("nice", "-n", "15", _sys2.executable, str(root / "scripts" / "calib_forecast.py"),
                                                          str(root / "data" / "brain.sqlite"), str(root / "data" / "fc_calib_live.json"), cwd=str(root),
                                                          stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.wait_for(pr.wait(), 1800)
            except Exception:  # noqa: BLE001
                log.exception("calib")
    tasks.append(asyncio.create_task(_calib_nightly()))
    if os.getenv("REPLAY") != "1":  # дані сервера → гілка ops-data на GitHub для сесій аналізу (вмикає OPS_GIT_TOKEN)
        from . import ops_export
        tasks.append(asyncio.create_task(ops_export.run(brain)))

    async def _tts_warm():  # українська озвучка: рушій і голос «Лада» готуються у фоні одразу після старту
        from . import tts
        await asyncio.sleep(20)
        if not tts.piper_ok():
            tts._install_bg()
        for k in ("lada", "tetiana", "mykyta", "oleksa"):
            try:
                await tts._ensure_model(k)
            except Exception as e:  # noqa: BLE001
                log.info("tts warm %s: %s", k, e)
        # голосові заготовки Sky Radio: озвучуються разово у фоні, далі радіо говорить без очікування (04.11)
        if not os.getenv("REPLAY") and (os.getenv("OPENAI_API_KEY") or os.getenv("GOOGLE_TTS_KEY")):
            from . import voicekit
            (asyncio.create_task(voicekit.warm(_say, _paid_ok)) if (_paid_ok() or (os.getenv('GOOGLE_TTS_KEY') and _google_ok())) else None)
        for _ in range(60):  # рушій міг ще ставитися — чекаємо й «розігріваємо» голос, щоб перше сповіщення звучало одразу
            if tts.piper_ok():
                await tts.speak("Готово", "lada")
                break
            await asyncio.sleep(10)
    tasks.append(asyncio.create_task(_tts_warm()))
    if os.getenv("REPLAY") != "1" and os.getenv("AUTO_SOURCES", "1") == "1":
        tasks.append(asyncio.create_task(DISCOVER.run()))
    if os.getenv("LAN_TLS", "1") == "1":
        tasks.append(asyncio.create_task(lan_tls.run()))
    if os.getenv("REPLAY") != "1":
        tasks.append(asyncio.create_task(telegram_src.run(on_message) if config.TG_SESSION else webmon.run(on_message)))
        tasks.append(asyncio.create_task(learn_history()))
    log.info("Тривога запущена: %d каналів", len(config.CHANNELS))
    yield
    try:
        STATE_FILE.write_bytes(tracker.dump_state())  # при зупинці — останній стан
    except Exception as e:  # noqa: BLE001
        log.warning("стан трекера при зупинці: %s", e)
    for t in tasks:
        t.cancel()


app = FastAPI(title="NAVRYX SKY", lifespan=lifespan)
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)  # geojson і скрипти стискаються в 3-5 разів

from .visits import PAGES, Visits  # noqa: E402

VISITS = Visits()


def _client_ip(scope_client, headers) -> str | None:
    xff = headers.get("x-forwarded-for")
    return xff.split(",")[0].strip() if xff else (scope_client[0] if scope_client else None)


# ---------- захист (04.11, незалежна оцінка): ліміти на платні ендпоінти, службове лише для власника, заголовки безпеки
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
RATE = {"/api/tts": (30, 60), "/api/stt": (6, 60), "/api/live": (8, 60), "/api/ask": (8, 60), "/api/radio": (12, 60), "/api/voice": (20, 60),
        "/api/tts/check": (3, 60), "/api/brief": (6, 60), "/api/llm/check": (3, 60), "/api/llm/report": (6, 60)}
_hits: dict = {}


def _is_admin(request) -> bool:
    import hmac
    tok = request.headers.get("x-admin-token") or request.query_params.get("admin") or ""
    return bool(ADMIN_TOKEN) and hmac.compare_digest(tok, ADMIN_TOKEN)


@app.middleware("http")
async def guard(request, call_next):
    path = request.url.path
    lim = RATE.get(path) or (RATE.get("/api/voice") if path.startswith("/api/voice/") else None)
    if lim and not _is_admin(request):
        ip = request.headers.get("cf-connecting-ip") or _client_ip(request.client, request.headers) or "?"
        now = time.time()
        q = [x for x in _hits.get((ip, path), []) if now - x < lim[1]]
        if len(q) >= lim[0]:
            return JSONResponse({"ok": False, "why": "rate_limited"}, status_code=429, headers={"Retry-After": str(lim[1])})
        q.append(now)
        _hits[(ip, path)] = q
        if len(_hits) > 20000:
            _hits.clear()
    resp = await call_next(request)
    h = resp.headers
    h.setdefault("Strict-Transport-Security", "max-age=31536000")
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "SAMEORIGIN")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("Permissions-Policy", "microphone=(self), geolocation=(self), camera=(self)")
    if path.startswith("/api/") and "cache-control" not in h:
        h["Cache-Control"] = "no-store"
    return resp


@app.middleware("http")
async def count_visits(request, call_next):
    """Відвідування сторінок (без cookies і без збереження IP, див. app/visits.py)."""
    resp = await call_next(request)
    if request.method == "GET" and request.url.path in PAGES and resp.status_code < 400:
        try:
            VISITS.hit(_client_ip(request.client, request.headers), request.headers.get("user-agent"), "view")
        except Exception:  # noqa: BLE001
            pass
    return resp


@app.get("/api/admin/envkey")
async def api_envkey():
    """ПУБЛІЧНИЙ ключ сервера: ним дія GitHub шифрує ключі власника (розшифрувати може лише цей сервер)."""
    from fastapi.responses import PlainTextResponse
    from . import secrets_sync
    return PlainTextResponse(secrets_sync.public_pem())


@app.get("/api/ask")
async def api_ask(obl: str = "") -> dict:
    """«Що зараз відбувається?» для області: коротке пояснення моделлю лише за даними SKY (кеш 90 с)."""
    if not AIX or not obl:
        return {"ok": False, "text": "ШІ ще не підключено."}
    return await AIX.explain(obl[:40])


@app.get("/api/llm/report")
async def api_llm_report(request: Request) -> dict:
    """Самонавчання: згода моделі з правилами за добу, пропозиції словника, підсумок ночі (без ключів). Лише власнику."""
    if not _is_admin(request):
        return JSONResponse({"ok": False, "why": "admin_only"}, status_code=403)
    import subprocess as _sp
    import sys as _sys
    root = Path(__file__).resolve().parent.parent
    out = {"stats": LLMX.stats()}
    try:
        r = _sp.run([_sys.executable, str(root / "scripts" / "llm_report.py"), str(root / "data" / "llm.jsonl")],
                    capture_output=True, text=True, timeout=60)
        out["report"] = json.loads(r.stdout or "{}")
    except Exception as e:  # noqa: BLE001
        out["report_error"] = type(e).__name__
    for k, f in (("dictionary", "llm_dict.json"), ("night", "llm_night.json")):
        p_ = root / "data" / f
        if p_.exists():
            out[k] = json.loads(p_.read_text(encoding="utf-8"))
    return out


def _live_args(t: float, obl: str, lat: float | None, lon: float | None):
    since = t if t > 0 else time.time() - 1800
    home = (lon, lat) if lat is not None and lon is not None else None
    return max(time.time() - 12 * 3600, since), home, (obl or None)


@app.get("/api/since")
def api_since(t: float = 0, obl: str = "", lat: float | None = None, lon: float | None = None):
    """«Поки вас не було»: що змінилося з моменту t для району людини (лише перевірені дані)."""
    from . import live
    since, home, ob = _live_args(t, obl, lat, lon)
    return JSONResponse(live.diff(state(), HIST, tracker, since, home, ob))


@app.post("/api/live")
async def api_live(req: Request):
    """Живий ефір: сценарій для мапи (репліки + дозволені дії) з різниці та, за потреби, питання людини."""
    from . import live
    b = await req.json()
    since, home, ob = _live_args(float(b.get("t") or 0), b.get("obl") or "", b.get("lat"), b.get("lon"))
    bbox = b.get("bbox") if isinstance(b.get("bbox"), list) else None
    d = live.diff(state(), HIST, tracker, since, home, ob, bbox)
    q = (b.get("q") or "").strip()[:300] or None
    out = await live.narrate(LLMX, d, q)
    return {"diff": d, **out}


@app.post("/api/stt")
async def api_stt(req: Request):
    """Голосове питання з iPhone: аудіо (до ~3 МБ) → текст. Аудіо не зберігається."""
    body = await req.body()
    if not body or len(body) > 3_000_000:
        return {"ok": False, "text": ""}
    txt, by = await LLMX.transcribe(body, req.headers.get("content-type", ""))
    return {"ok": bool(txt), "text": txt, "by": by}


@app.get("/api/radio")
async def api_radio(t: float = 0, obl: str = "", lat: float | None = None, lon: float | None = None, scope: str = "near", sid: str = "", radius: float = 25, g: int = 0, a: int = 0):
    """«Радіо SKY»: один голосовий випуск — свій регіон / сусідні області / уся Україна."""
    from . import live
    since, home, ob = _live_args(t, obl, lat, lon)
    sc = {"region": "near", "neighbors": "oblast"}.get(scope, scope)
    sc = sc if sc in ("near", "oblast", "country") else "near"
    return await live.radio(LLMX, state(), HIST, tracker, since, home, ob or "", sc, sid[:40], max(5.0, min(100.0, radius)), greeted=bool(g), after=bool(a))


@app.get("/api/health")
async def api_health() -> dict:
    """Коротка перевірка для зовнішнього нагляду: сервер живий і дані справді надходять (не лише відкривається сторінка)."""
    now = time.time()
    ws = webmon.state()
    off = alerts.state()
    a_age = int(now - (off.get("updated") or 0)) if off.get("updated") else None
    live_share = round(ws.get("live", 0) / max(1, ws.get("channels", 1)), 2)
    problems = []
    if os.getenv("REPLAY") != "1":
        if not off.get("ok") or a_age is None or a_age > 300:
            problems.append("official_alerts_stale")
        if live_share < 0.3 and not config.TG_SESSION:
            problems.append("channels_stale")
    return {"ok": not problems, "problems": problems, "now": int(now), "alerts_age": a_age, "channels_live": live_share,
            "msg_age": int(now - FRESH["any"]) if FRESH["any"] else None, "uptime": int(now - started), "version": "2026-11-04.1"}


@app.post("/api/brief")
async def api_brief(req: Request) -> dict:
    """Створити картку-зведення по області для поширення (без дому користувача)."""
    from . import brief
    try:
        body = await req.json()
    except Exception:  # noqa: BLE001
        body = {}
    obl = str(body.get("obl") or "")[:40]
    if not obl:
        return JSONResponse({"ok": False, "why": "obl"}, status_code=400)
    b = brief.make(state(), obl)
    return {"ok": True, "id": b["id"], "url": f"/b/{b['id']}"}


@app.get("/b/{bid}")
async def brief_page(bid: str, request: Request):
    from fastapi.responses import HTMLResponse
    from . import brief
    b = brief.get(bid[:20])
    if not b:
        return HTMLResponse("<!doctype html><meta charset=utf-8><p style='font-family:system-ui'>Зведення не знайдено. <a href='/'>Жива мапа</a></p>", status_code=404)
    base = f"{request.url.scheme}://{request.url.netloc}"
    return HTMLResponse(brief.page(b, base), headers={"Cache-Control": "public, max-age=60"})


@app.get("/api/llm")
async def api_llm(request: Request) -> dict:
    """Публічно — лише чи ввімкнено ШІ; провайдери, лічильники й помилки — тільки власнику (ADMIN_TOKEN)."""
    st = LLMX.stats()
    if _is_admin(request):
        return st
    return {"enabled": st["enabled"], "assist": st["assist"]}


@app.get("/api/llm/usage")
async def api_llm_usage(request: Request) -> dict:
    """Скільки запитів пішло на безкоштовні й платні моделі по днях, скільки зекономлено кешем і згодою дешевих моделей."""
    from .llm import COST, USAGE
    u = LLMX._usage
    if u is None:
        try:
            u = json.loads(USAGE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            u = {}
    out = {}
    for d, row in sorted(u.items()):
        free = sum(v for k, v in row.items() if k.startswith("ok:") and COST.get(k[3:], 2) == 0)
        paid = sum(v for k, v in row.items() if k.startswith("ok:") and COST.get(k[3:], 2) > 0)
        out[d] = {"free_ok": free, "paid_ok": paid, "saved_cache": row.get("saved:cache", 0), "saved_agree": row.get("saved:agree", 0),
                  "saved_radio": row.get("saved:radio", 0),
                  "tts_paid_chars": sum(v for k, v in row.items() if k.startswith("tts_chars:")),
                  "tts_paid": sum(v for k, v in row.items() if k in ("tts:openai", "tts:gemini")),
                  "tts_cached": sum(v for k, v in row.items() if k.endswith("-cache") and k.startswith("tts:"))}
        if _is_admin(request):
            out[d]["raw"] = row
    return {"days": out} | ({"cost": COST} if _is_admin(request) else {})


_llm_check: dict = {}


@app.get("/api/llm/check")
async def api_llm_check(request: Request) -> dict:
    """Пробний мінімальний запит до кожної моделі: хто живий, у кого немає кредитів, неправильний ключ чи модель. Не частіше разу на 2 хв."""
    if not _is_admin(request):
        return JSONResponse({"ok": False, "why": "admin_only"}, status_code=403)
    if _llm_check.get("t", 0) > time.time() - 120:
        return _llm_check
    import httpx as _h
    out = {}
    async with _h.AsyncClient() as cli:
        async def one(prov):
            t0 = time.time()
            try:
                r = await LLMX._one(cli, prov, "Відповідай одним словом.", "Скажи: так", None, None, 5)
                LLMX.off.pop(prov[0], None)
                LLMX._ok(prov[0])
                out[prov[0]] = {"ok": True, "model": prov[3], "ms": int((time.time() - t0) * 1000), "reply": str(r)[:20]}
            except Exception as e:  # noqa: BLE001
                LLMX._fail(prov[0], e)
                out[prov[0]] = {"ok": False, "model": prov[3], "error": LLMX.err_by.get(prov[0], "")[:200]}
        await asyncio.gather(*(one(p_) for p_ in LLMX._chain()))
    _llm_check.clear()
    _llm_check.update({"t": int(time.time()), "providers": out})
    return _llm_check


@app.get("/api/visits")
def api_visits(days: int = 30):
    st = VISITS.stats(max(1, min(days, 365)))
    st["online"] = len(clients)
    try:  # пристрої з увімкненими сповіщеннями: найточніша оцінка «встановили й користуються» (на iPhone push можливий лише зі встановленого)
        st["push_devices"] = pushsvc.db.execute("SELECT COUNT(*) FROM websubs").fetchone()[0] + pushsvc.db.execute("SELECT COUNT(*) FROM subs").fetchone()[0]
    except Exception:  # noqa: BLE001
        st["push_devices"] = None
    return JSONResponse(st)


@app.post("/api/visits/app")
def api_visits_app(request: Request, k: str = "app"):
    """Запуск із встановленого застосунку або подія встановлення (без cookies і IP, див. app/visits.py)."""
    try:
        VISITS.app_hit(_client_ip(request.client, request.headers), request.headers.get("user-agent"), k)
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse({"ok": True})


def _paid_ok() -> bool:
    import datetime as _dt
    from zoneinfo import ZoneInfo
    cap = int(os.getenv("TTS_DAILY_CHARS", "40000"))  # 04.11 власник: «щоб не витрачати кошти» — платний голос ≤ ≈$0,5 на добу
    day = (LLMX._usage or {}).get(_dt.datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%Y-%m-%d"), {})
    return sum(v for k, v in day.items() if k.startswith("tts_chars:") and k not in ("tts_chars:google", "tts_chars:openai")) < cap


def _google_ok() -> bool:
    """Google Chirp 3 HD: перший 1 млн символів на місяць безкоштовний; тримаємось нижче (GOOGLE_FREE_CHARS, за замовчуванням 900 тис.)."""
    import datetime as _dt
    from zoneinfo import ZoneInfo
    mon = _dt.datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%Y-%m")
    used = sum(v.get("tts_chars:google", 0) for d, v in (LLMX._usage or {}).items() if str(d).startswith(mon) and isinstance(v, dict))
    return used < int(os.getenv("GOOGLE_FREE_CHARS", "900000"))


_BY: dict = {}


async def _say(text: str, voice: str = "radio", rate: float = 1.0):
    """Озвучка з обліком: нові (не з кешу) символи йдуть у ліміти (денний платний, місячний безкоштовний Google)."""
    from . import tts
    data, why = await tts.speak(text, voice, rate, paid=_paid_ok(), google=_google_ok())
    if data and why in ("openai", "gemini", "google"):
        LLMX.count("tts_chars:" + why, len(text))
    _BY[why] = _BY.get(why, 0) + 1
    return data, why


@app.get("/api/voice/alert")
async def api_voice_alert(text: str, voice: str = "lada", rate: float = 1.0):
    """Голосове сповіщення із заготовок: картка розбивається на короткі фрази з округленими числами; кожна фраза озвучується
    один раз на голос, далі — з кешу, без витрат (04.11, власник: «коштів не вистачить озвучувати все»)."""
    from fastapi import Response
    from . import voicekit
    fr = voicekit.alert_frags(text[:300])
    if not fr:
        return JSONResponse({"ok": False, "why": "empty"}, status_code=400)
    v = voice if voice in ("lada", "tetiana", "mykyta", "oleksa", "radio") else "lada"
    r = max(0.7, min(1.5, rate))
    data, why = await voicekit.render(fr, lambda x: _say(x, v, r))
    LLMX.count("tts:alert-" + why)
    if not data:
        return JSONResponse({"ok": False, "why": why}, status_code=503)
    return Response(data, media_type="audio/wav" if data[:4] == b"RIFF" else "audio/mpeg", headers={"Cache-Control": "max-age=86400", "X-TTS": why})


@app.get("/api/voice/{sid}")
async def api_voice(sid: str):
    """Голос Sky Radio із заготовок (voicekit): склейка вже озвучених фраз, без нового синтезу для знайомих фраз."""
    from fastapi import Response
    from . import voicekit
    item = voicekit.SEQ.get(sid[:16])
    if not item:
        return JSONResponse({"ok": False, "why": "unknown"}, status_code=404)
    data, why = await voicekit.render(item[1], _say)
    LLMX.count("tts:" + why)
    if not data:
        return JSONResponse({"ok": False, "why": why}, status_code=503)
    return Response(data, media_type="audio/wav" if data[:4] == b"RIFF" else "audio/mpeg", headers={"Cache-Control": "max-age=86400", "X-TTS": why})


@app.get("/api/tts")
async def api_tts(text: str, voice: str = "lada", rate: float = 1.0):
    """Українська озвучка (Piper). 503, поки ставиться рушій або голос; клієнт тоді говорить голосом пристрою."""
    from fastapi import Response
    from . import tts
    cap = int(os.getenv("TTS_DAILY_CHARS", "40000"))  # 04.11: ≈$0,5 на добу максимум; понад — запасний голос, щоб не спустошити рахунок
    import datetime as _dt
    from zoneinfo import ZoneInfo
    day = (LLMX._usage or {}).get(_dt.datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%Y-%m-%d"), {})
    paid_ok = sum(v for k, v in day.items() if k.startswith("tts_chars:") and k not in ("tts_chars:google", "tts_chars:openai")) < cap
    data, why = await tts.speak(text, voice, rate, paid=paid_ok, google=_google_ok())
    LLMX.count("tts:" + (why or "none").split(":")[0])
    if data and why in ("openai", "gemini", "google"):
        LLMX.count("tts_chars:" + why, len(text))
    if not data:
        return JSONResponse({"ok": False, "why": why, **tts.status()}, status_code=503)
    mt = "audio/mpeg" if why.startswith(("google", "openai")) else "audio/wav"
    return Response(data, media_type=mt, headers={"Cache-Control": "max-age=86400", "X-TTS": why})


@app.get("/api/msgs")
def api_msgs(kind: str | None = None, type: str | None = None, hours: float = 3, q: str | None = None, limit: int = 200):
    """Журнал розібраних повідомлень, докази для самоаналізу (що написав канал і як ми це зрозуміли)."""
    sql, args = "SELECT t, src, link, kind, type, places, text FROM msg WHERE t >= ?", [time.time() - hours * 3600]
    if kind:
        sql += " AND kind = ?"; args.append(kind)
    if type:
        sql += " AND type = ?"; args.append(type)
    if q:
        sql += " AND text LIKE ?"; args.append(f"%{q}%")
    rows = brain.db.execute(sql + " ORDER BY t DESC LIMIT ?", (*args, min(limit, 1000))).fetchall()
    return [{"t": int(r[0]), "src": r[1], "link": r[2], "kind": r[3], "type": r[4], "places": r[5], "text": r[6]} for r in rows]


@app.get("/api/tts/check")
async def api_tts_check(request: Request):
    """Діагностика озвучки: хто зараз говорить (openai / gemini / piper). Публічно — без тексту помилок; власнику — повністю."""
    from . import tts
    tts._off.clear()  # ручна перевірка: знову пробуємо всіх (наприклад, після поповнення рахунку)
    data, why = await tts.speak(f"Перевірка голосу. Харків, Чугуїв, Балаклія. {int(time.time()) % 1000}", "lada", 1.0)
    if _is_admin(request):
        return {"ok": bool(data), "by": why} | tts.status()
    return {"ok": bool(data), "voice": "neural" if why.startswith(("openai", "gemini", "google")) else "basic" if data else "none"}


@app.get("/api/enemy/summary")
def enemy_summary():
    """Діагностика точкових об'єктів DeepState: типи геометрій, категорії, найчастіші назви (щоб звірити класифікацію з реальними даними)."""
    f = ROOT / "data" / "enemy_summary.json"
    return JSONResponse(json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"status": "ще не завантажено"})


@app.get("/api/tts/status")
def api_tts_status(request: Request):
    from . import tts
    st = tts.status()
    if _is_admin(request):
        return st
    # публічно — без назв сторонніх провайдерів: лише чи є природний голос і чи готовий запасний
    return {"neural": bool(st.get("openai") or st.get("gemini") or st.get("google")), "ready": bool(st.get("piper")), "last_codes": tts.codes(),
            "by": dict(_BY), "g_key": bool(st.get("google")), "g_ok": _google_ok(), "paid_ok": _paid_ok(),
            "voices": [{"key": v["key"], "name": v["name"]} for v in st.get("voices", [])]}


@app.get("/api/sources_auto")
def api_sources_auto():
    """Автопошук джерел: прийняті (з доказами), перевірені в останньому проході, відхилені."""
    st = DISCOVER.state
    return {"last": st["last"], "every_h": 2, "accepted_n": len(st["accepted"]), "accepted": st["accepted"], "checked": st["checked"],
            "rejected_n": len(st["rejected"]), "rejected_recent": sorted(st["rejected"].items(), key=lambda kv: -kv[1].get("t", 0))[:30]}


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


@app.get("/api/track/{tid}")
async def api_track(tid: str):
    ev = tracker.track_evidence(tid)
    if ev is None:
        return JSONResponse({"error": "немає такої цілі"}, status_code=404)
    return JSONResponse(ev)


@app.get("/api/webpush/key")
async def webpush_key():
    return {"key": await asyncio.to_thread(pushsvc.public_key)}


@app.post("/api/webpush/subscribe")
async def webpush_subscribe(body: dict):
    try:
        ok = pushsvc.web_register(body.get("sub") or {}, float(body.get("lon", 0)), float(body.get("lat", 0)), bool(body.get("pre", True)), body.get("zones"))
    except (TypeError, ValueError):
        ok = False
    return JSONResponse({"ok": ok}, status_code=200 if ok else 400)


_WP_TEST: dict[str, float] = {}


@app.post("/api/webpush/test")
async def webpush_test(body: dict):
    """Тестове сповіщення на цей пристрій (перевірити, що доходить на заблокований екран). Не частіше разу на хвилину."""
    ep = str(body.get("endpoint", ""))
    row = pushsvc.db.execute("SELECT sub FROM websubs WHERE endpoint=?", (ep,)).fetchone()
    if not row:
        return JSONResponse({"ok": False, "why": "цей пристрій не підписаний"}, status_code=404)
    if time.time() - _WP_TEST.get(ep, 0) < 60:
        return JSONResponse({"ok": False, "why": "не частіше разу на хвилину"}, status_code=429)
    _WP_TEST[ep] = time.time()
    await pushsvc._web_send([{"to": ep, "sub": row[0], "title": "🟠 Тест · так виглядатиме загроза",
                              "body": "12 км на захід від вас · останнє місце: Люботин\nКурс → Пересічне · на північний схід\n"
                                      "2 незалежні джерела · місце о " + time.strftime("%H:%M") + "\nЦе перевірка: сповіщення доходять.",
                              "data": {"track": "test", "type": "shahed"}}])
    return {"ok": True}


@app.post("/api/webpush/unsubscribe")
async def webpush_unsubscribe(body: dict):
    pushsvc.web_unregister(str(body.get("endpoint", "")))
    return {"ok": True}


@app.post("/api/push/unregister")
async def push_unregister(body: dict):
    pushsvc.unregister(str(body.get("token", "")))
    return {"ok": True}


@app.get("/api/daily")
async def api_daily(d: str | None = None):
    """Мапа доби 09:00→09:00. d, дата ранку, коли доба закінчилась; без d, остання завершена."""
    import re as _re
    day = d if d and _re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) else last_finished()
    if day > current_day():
        return JSONResponse({"error": "доба ще не почалась"}, status_code=404)
    return JSONResponse(await daily.get(day))


_AN: list = [0.0, None]


@app.get("/api/analysis")
def api_analysis():
    """Аналітична довідка: хвиля, напрямки, цілі, порівняння з попередніми ночами, швидкість і незалежність джерел,
    самоперевірка прогнозу. Кожен розділ, з числами й id цілей, з яких зроблено висновок."""
    from .analyst import analyze
    if time.time() - _AN[0] > 30 or _AN[1] is None:
        snap = state()
        _AN[0], _AN[1] = time.time(), analyze(snap, HIST, brain, snap["now"])
    return JSONResponse(_AN[1])


@app.get("/api/area")
def api_area(lat: float, lon: float, r: float = 25, days: int = 14):
    """Статистика району: скільки цілей проходило ≤ r км від точки за останні доби, години, боки, типи (за мапами доби)."""
    from .areastats import area_stats
    if not (43 < lat < 53 and 20 < lon < 42):
        return JSONResponse({"error": "точка поза Україною"}, status_code=400)
    return JSONResponse(area_stats(round(lat, 2), round(lon, 2), max(5.0, min(r, 60.0)), max(1, min(days, 60))))


def _lite_frame(f: dict) -> dict:
    """Кадр без списку публікацій (≈75% обсягу): для програвання вистачає позицій і рівнів."""
    return {**f, "tracks": [{**t, "ev": {k: v for k, v in (t.get("ev") or {}).items() if k != "items"}} for t in f["tracks"]]}


@app.get("/api/history")
def api_history(full: int = 0, hours: float = 12):
    """Машина часу. За замовчуванням, легкі кадри (≈1.8 МБ замість 7.5 МБ JSON); докази кадру, /api/history/frame."""
    since = time.time() - max(0.5, min(hours, 12)) * 3600
    fr = [f for f in HIST if f["t"] >= since]
    return JSONResponse({"frames": fr if full else [_lite_frame(f) for f in fr]})


@app.get("/api/counts")
def api_counts(hours: float = 3, typ: str = "shahed"):
    """Діагностика лічильника: чому «цілей більше, ніж у сусідів». Розклад активних треків типу на складові:
    множники ×N, давність останньої згадки, одне джерело, і скільки треків злилося б при ширшому порозі склеювання."""
    import math
    snap = state()
    now = snap["now"]
    act = [t for t in snap["tracks"] if t["status"] == "active" and t["type"] == typ]
    units = sum((t.get("count") or 1) for t in act)
    age = [max(0, now - t["last"]) / 60 for t in act]
    buckets = {"<5": 0, "5-10": 0, "10-15": 0, "15-25": 0, ">25": 0}
    for a in age:
        buckets["<5" if a < 5 else "5-10" if a < 10 else "10-15" if a < 15 else "15-25" if a < 25 else ">25"] += 1
    single = sum(1 for t in act if len(t.get("srcs") or []) <= 1)
    est = sum(1 for t in act if t.get("pos_est") or t.get("nopos"))
    # скільки лишилося б треків, якби склеювати все одного типу в радіусі R км із різницею останньої згадки до 15 хв
    def km(a, b):
        return math.hypot((a["lon"] - b["lon"]) * 111.32 * math.cos(math.radians(49)), (a["lat"] - b["lat"]) * 110.57)
    def clusters(r):
        left, n = list(act), 0
        while left:
            seed = left.pop(0); n += 1
            grp, i = [seed], 0
            while i < len(grp):
                g = grp[i]; i += 1
                for o in list(left):
                    if km(g, o) <= r and abs(g["last"] - o["last"]) <= 900:
                        left.remove(o); grp.append(o)
        return n
    merge = {str(r): clusters(r) for r in (7, 15, 30, 50)}
    # історія: середнє й пік одночасних треків і «одиниць» (з ×N) за останні години
    since = now - max(0.5, min(hours, 12)) * 3600
    fr = [f for f in HIST if f["t"] >= since]
    series = [(len([t for t in f["tracks"] if t["type"] == typ]), sum((t.get("count") or 1) for t in f["tracks"] if t["type"] == typ)) for f in fr]
    hist = {"frames": len(series),
            "tracks_avg": round(sum(s[0] for s in series) / len(series), 1) if series else None, "tracks_peak": max((s[0] for s in series), default=None),
            "units_avg": round(sum(s[1] for s in series) / len(series), 1) if series else None, "units_peak": max((s[1] for s in series), default=None)}
    merged = sum(1 for t in tracker.tracks if getattr(t, "merged", None) and t.type == typ)
    return {"now": int(now), "type": typ, "tracks": len(act), "units": units, "multiplier_extra": units - len(act), "merged_as_duplicates": merged,
            "with_count_gt1": sum(1 for t in act if (t.get("count") or 1) > 1),
            "age_since_last_min": buckets, "single_source": single, "pos_estimated": est,
            "tracks_if_merged_within_km": merge, "life_min": TYPES[typ]["life"] / 60 if typ in TYPES else None,
            "history": hist,
            "rows": [{"id": t["id"], "count": t.get("count"), "age_min": round(max(0, now - t["last"]) / 60, 1), "srcs": len(t.get("srcs") or []),
                      "est": bool(t.get("pos_est") or t.get("nopos")), "next": t.get("next")} for t in sorted(act, key=lambda t: t["last"])]}


@app.get("/api/selfcheck")
def api_selfcheck():
    """Останній щоденний самоаналіз (падіння парсера, підозрілі розбори з прикладами, бектест, джерела)."""
    if not SELFCHECK_FILE.exists():
        return {"error": "самоаналізу ще не було (запускається щодня о ~05:40)"}
    return JSONResponse(json.loads(SELFCHECK_FILE.read_text(encoding="utf-8")))


@app.get("/api/journal")
def api_journal(hours: float = 24, q: str | None = None, src: str | None = None, kind: str | None = None, limit: int = 300):
    """Журнал публічних повідомлень каналів (як розібрав SKY) — докази для виправлень і перевірки регресій."""
    since = time.time() - max(0.1, min(hours, 24 * 14)) * 3600
    sql, args = "SELECT t, src, link, kind, type, places, text FROM msg WHERE t > ?", [since]
    if src:
        sql += " AND src = ?"; args.append(src)
    if kind:
        sql += " AND kind = ?"; args.append(kind)
    if q:
        sql += " AND lower(text) LIKE ?"; args.append("%" + q.lower() + "%")
    sql += " ORDER BY t DESC LIMIT ?"; args.append(max(1, min(limit, 5000)))
    with brain.lock:
        rows = brain.db.execute(sql, args).fetchall()
    return {"n": len(rows), "items": [{"t": int(t), "src": s_, "link": l_, "kind": k_, "type": ty, "places": p_, "text": (tx or "")[:400]}
                                      for t, s_, l_, k_, ty, p_, tx in rows]}


@app.get("/api/fusion")
def api_fusion(fresh: int = 0):
    """Звіт самоперевірки злиття напрямку: скільки пар у журналі прогнозів, точність на днях, яких модель не бачила, рішення."""
    from . import fusion as _fusion
    if fresh:
        return _fusion.evaluate(brain.db)
    return getattr(tracker, "fusion", None) or {"on": False, "why": "перевірки ще не було", "total": brain.db.execute("SELECT count(*) FROM sqlite_master WHERE name='fcast'").fetchone()[0] and brain.db.execute("SELECT count(*) FROM fcast").fetchone()[0]}


@app.get("/api/changes")
def api_changes(lon: float, lat: float, since: float, r: float = 60, obl: str | None = None, raion: str | None = None):
    """«Що змінилося, поки мене не було?» для точки: тривога, нові цілі (з першоджерелами й перепостами),
    уточнені курси (хто й коли), наближення/віддалення, втрачені й закриті позначки."""
    from .changes import changes
    from .tracker import TYPES as _T
    snap = state()
    since = max(since, time.time() - 12 * 3600)
    return changes(HIST, snap, lon, lat, since, r, {k: v["name"] for k, v in _T.items()}, tracker.track_evidence, obl, raion)


@app.get("/api/near")
def api_near(lon: float, lat: float, r: float = 60):
    """Коли востаннє позначка цілі була в межах r км від точки, за кадрами машини часу (до 12 год) і поточним станом."""
    from .geo import dist_km, to_xy
    H = to_xy(lat, lon)
    last, hours = None, 0.0
    if HIST:
        hours = round((time.time() - HIST[0]["t"]) / 3600, 1)
    for f in reversed(HIST):
        if any(dist_km(H, to_xy(t["lat"], t["lon"])) <= r for t in f["tracks"]):
            last = f["t"]
            break
    for t in tracker.snapshot()["tracks"]:
        if t["status"] != "closed" and dist_km(H, to_xy(t["lat"], t["lon"])) <= r:
            last = max(last or 0, t["last"])
    return {"last": last, "hours": hours, "r": r}


@app.get("/api/history/frame")
def api_history_frame(t: float):
    """Повний кадр (з доказами «що було відомо тоді»), найближчий до t не пізніше нього."""
    best = None
    for f in HIST:
        if f["t"] <= t + 30:
            best = f
        else:
            break
    return JSONResponse(best or {})


@app.get("/api/lan")
def api_lan():
    """Адреси цього комп'ютера в локальній мережі, щоб відкрити «Тривогу» на телефоні (QR у налаштуваннях)."""
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
        VISITS.hit(_client_ip(ws.client, ws.headers), ws.headers.get("user-agent"), "ws")
        VISITS.online(len(clients))
    except Exception:  # noqa: BLE001
        pass
    try:
        await ws.send_text(json.dumps(state(), ensure_ascii=False))
        while True:
            m = await ws.receive_text()  # ping / hidden / visible від клієнта
            if m == "hidden":
                HIDDEN.add(ws)
            elif m == "visible":
                HIDDEN.discard(ws)
                await ws.send_text(json.dumps(state(), ensure_ascii=False))  # повернувся — одразу свіжий стан
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)
        HIDDEN.discard(ws)


@app.get("/data/{name}")
def data_file(name: str):
    allowed = {"oblasts.geojson", "raions.geojson", "occupied.geojson", "enemy_objects.geojson", "hromadas.geojson", "outside.geojson", "ua.geojson"}
    if name not in allowed or not (ROOT / "data" / name).exists():
        return JSONResponse({"type": "FeatureCollection", "features": []} if name in ("occupied.geojson", "enemy_objects.geojson") else {"error": "not found"},
                            status_code=200 if name in ("occupied.geojson", "enemy_objects.geojson") else 404)
    return FileResponse(ROOT / "data" / name, media_type="application/geo+json")


class FreshStatic(StaticFiles):
    """Оболонка застосунку завжди перевіряється на свіжість (ETag): телефон не тримає стару версію годинами."""
    async def get_response(self, path, scope):
        r = await super().get_response(path, scope)
        if path == "" or path.endswith((".html", ".js", ".css", ".webmanifest")) or "." not in path.rsplit("/", 1)[-1]:
            r.headers["Cache-Control"] = "no-cache"
        return r


app.mount("/", FreshStatic(directory=WEB, html=True), name="web")
