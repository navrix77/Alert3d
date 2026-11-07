"""Офіційні тривоги (alerts.in.ua): червоний — тривога на всю область, жовтий — у частині області."""
from __future__ import annotations

import asyncio
import re
import logging
import time

import httpx

from . import config

log = logging.getLogger("alerts")
URL = "https://api.alerts.in.ua/v1/alerts/active.json"
UBILLING = "https://ubilling.net.ua/aerialalerts/"
ACTIVE_MD = "https://api.alerts.in.ua/v3/alerts/active.md"  # відкрите зведення alerts.in.ua: райони/громади, червоний/жовтий  # без токена: стан областей (API В. Клименка)


from pathlib import Path as _P
SEP_FILE = _P(__file__).resolve().parent.parent / "data" / "sep_hromadas.json"
SEP_SEED = {1174}
OBLS = ["Вінницька", "Волинська", "Луганська", "Дніпропетровська", "Донецька", "Житомирська", "Закарпатська", "Запорізька",
        "Івано-Франківська", "Київська", "Кіровоградська", "Львівська", "Миколаївська", "Одеська", "Полтавська", "Рівненська",
        "Сумська", "Тернопільська", "Харківська", "Херсонська", "Хмельницька", "Черкаська", "Чернігівська", "Чернівецька"]  # м. Харків (Харківська громада): окремий статус в офіційних даних

class OfficialAlerts:
    def __init__(self) -> None:
        self.oblast_levels: dict[str, int] = {}
        self.raions: list[str] = []
        self.updated = 0.0
        self.ok = False
        self.error: str | None = None
        self.raion_levels: dict[str, int] = {}
        self.hromada_levels: dict[int, int] = {}
        self.points: list[list] = []
        self.source = ""
        # громади-міста з власним офіційним статусом, окремим від району (м. Харків тощо): для дому в такому місті діє статус міста,
        # а не району (04.11: район під тривогою, а місто — ні; SKY писав «тривога у вашому районі»). Поповнюється з даних «м. …»
        self.sep: set[int] = set(SEP_SEED)
        try:
            import json as _j
            self.sep |= set(_j.loads(SEP_FILE.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    @staticmethod
    def short(name: str) -> str:
        return name.replace(" область", "").replace("м. ", "").replace(" район", "").strip()

    def apply(self, payload: dict) -> None:
        lv: dict[str, int] = {}
        raions: set[str] = set()
        for a in payload.get("alerts", []):
            if a.get("alert_type") not in (None, "air_raid"):
                continue
            ltype = a.get("location_type")
            obl = self.short(a.get("location_oblast") or a.get("location_title") or "")
            if ltype == "oblast":
                lv[obl] = 2
            else:
                lv[obl] = max(lv.get(obl, 0), 1)
                if ltype == "raion":
                    raions.add(self.short(a.get("location_title", "")))
        self.oblast_levels, self.raions = lv, sorted(raions)
        self.updated, self.ok, self.error = time.time(), True, None

    async def run(self) -> None:
        if not config.ALERTS_TOKEN:
            await self.run_open()
            return
        headers = {"Authorization": f"Bearer {config.ALERTS_TOKEN}"}
        async with httpx.AsyncClient(timeout=10) as cli:
            while True:
                try:
                    r = await cli.get(URL, headers=headers)
                    r.raise_for_status()
                    self.apply(r.json())
                except Exception as e:  # мережа/ліміт — статус стане «застарілим», але не «відбій»
                    self.ok, self.error = False, str(e)[:200]
                    log.warning("alerts poll failed: %s", e)
                    await self.ualarm_once(cli)
                await asyncio.sleep(config.ALERTS_POLL_SEC)

    on_threat = None
    _seen_threats: set = set()
    THREAT = re.compile(r"^- \*\*(\d{1,2}):(\d{2}) — ([^*]+?)\*\* over ([^—]+?) — (.*)$", re.M)
    DIRW = [("north-east", 45), ("north-west", 315), ("south-east", 135), ("south-west", 225), ("northeast", 45), ("northwest", 315),
            ("southeast", 135), ("southwest", 225), ("north", 0), ("south", 180), ("east", 90), ("west", 270)]

    def _heading(self, d: str):
        """Курс з англійського тексту. «on a westward course» — курс; «to the east of Poltava region» — це положення,
        а не напрямок руху (раніше брали його як курс і цілі летіли в протилежний бік)."""
        for k, az in self.DIRW:  # 1) явний курс: «westward course», «heading west», «towards the west»
            if re.search(rf"{re.escape(k)}wards?\b|heading {re.escape(k)}\b|towards the {re.escape(k)}\b", d):
                return az
        for k, az in self.DIRW:  # 2) «to the east» лише якщо не «to the east of …» (положення)
            if re.search(rf"to the {re.escape(k)}\b(?!\s+of\b)", d):
                return az
        return None

    def threats(self, md: str) -> list[dict]:
        """Розділ «THREAT ACTIVITY»: офіційні/моніторингові фіксації цілей із місцем і курсом."""
        import datetime as _dt
        from zoneinfo import ZoneInfo
        i, j = md.find("## 4."), md.find("## 5.")
        if i < 0:
            return []
        out = []
        now = _dt.datetime.now(ZoneInfo("Europe/Kyiv"))
        for m in self.THREAT.finditer(md[i:j if j > i else None]):
            hh, mm, what, where, desc = m.groups()
            key = m.group(0)
            if key in self._seen_threats:
                continue
            self._seen_threats.add(key)
            w, d = what.lower(), desc.lower()
            if "bomb" in w:
                typ = "kab"
            elif "ballistic" in w or "ballistic" in d:
                typ = "ballistic"
            elif "missile" in w or "cruise" in d:
                typ = "cruise"
            elif "jet" in d or "реактив" in d:
                typ = "jet"
            elif "drone" in w or "uav" in w:
                typ = "shahed"
            else:
                continue
            uk = re.search(r"\(([^()]*[А-ЯІЇЄҐа-яіїєґ][^()]*)\)", where)
            if not uk:
                continue
            name = uk.group(1).strip()
            if name.endswith("область"):
                continue  # уся область — надто неточно для позиції цілі
            n = re.search(r"\((\d+) tracked\)", what)
            hd = self._heading(d)
            t = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            if t > now + _dt.timedelta(minutes=5):
                t -= _dt.timedelta(days=1)
            out.append({"t": t.timestamp(), "type": typ, "count": int(n.group(1)) if n else None, "place": name, "heading": hd, "text": desc.strip()})
        if len(self._seen_threats) > 4000:
            self._seen_threats = set(list(self._seen_threats)[-2000:])
        return out

    LINE = re.compile(r"^\*\*[^*]*\(([^)]*?) область\)\*\*(.*)$", re.M)

    @staticmethod
    def parse_areas(rest: str) -> list[tuple[str, int]]:
        """Обидва формати зведення:
        «A (А), B (Б) [yellow (drone level)]» і «red (...): A (А), B (Б); yellow (...): C (В)»."""
        body = rest.split("affected:", 1)[-1].split("The most recent", 1)[0]
        out = []
        for grp in body.split(";"):
            g = grp.strip()
            m = re.match(r"(red|yellow)\s*\([^)]*\)\s*:", g)
            if m:
                lv, g = (2 if m.group(1) == "red" else 1), g[m.end():]
            else:
                ms = re.search(r"\[(red|yellow)", g)
                lv = 2 if ms and ms.group(1) == "red" else 1
                g = g.split("[", 1)[0]
            for uk in re.findall(r"\(([^()]*[А-ЯІЇЄҐа-яіїєґ][^()]*)\)", g):
                out.append((uk.strip(), lv))
        return out

    def apply_md(self, md: str) -> None:
        """Розбір відкритого зведення alerts.in.ua (розділ «CURRENT WARNING STATUS»)."""
        i, j = md.find("## 3"), md.find("## 4")
        sec = md[i:j if j > i else None]
        obl: dict[str, int] = {}
        areas: dict[str, int] = {}
        area_obl: dict[str, str] = {}
        hrom = self._hromadas()
        for m in self.LINE.finditer(sec):
            name, rest = m.group(1).strip(), m.group(2)
            if name not in hrom["_oblasts"]:
                continue  # області РФ теж є у зведенні — пропускаємо
            if "affected:" not in rest:
                obl[name] = 2 if re.search(r"level:\s*red|\[red", rest) else 1
                continue
            got = self.parse_areas(rest)
            if not got:  # формат знову змінився — краще залити всю область, ніж пропустити тривогу
                obl[name] = 2 if "red" in rest else 1
                log.warning("alerts.in.ua: не розібрав райони для %s", name)
            for uk, lv in got:
                areas[uk] = max(areas.get(uk, 0), lv)
                area_obl[uk] = name
        self._finish(obl, areas, area_obl, "alerts.in.ua (відкрите зведення)")

    def _finish(self, obl: dict, areas: dict, area_obl: dict, source: str) -> None:
        hrom = self._hromadas()
        raions: dict[str, int] = {}
        points: list[list] = []
        hrom_poly: dict[int, int] = {}
        ap = lambda x: x.replace("’", "'").replace("ʼ", "'")
        rmap = {ap(r): r for r in hrom["_raions"]}
        for uk, lv in areas.items():
            if ap(uk) in rmap and uk.endswith(("ський", "цький", "зький", "ний")):
                r = rmap[ap(uk)]
                raions[r] = max(raions.get(r, 0), lv)
            else:
                key = uk.replace("м. ", "").strip()
                # справжні межі громади (а не коло): назва громади або місто → його громада, у межах цієї області
                ids = self.hromada_ids(key, area_obl.get(uk), uk.startswith("м. "))
                if ids and uk.startswith("м. ") and not set(ids) <= self.sep:
                    self.sep |= set(ids)
                    try:
                        import json as _j
                        SEP_FILE.parent.mkdir(parents=True, exist_ok=True)
                        SEP_FILE.write_text(_j.dumps(sorted(self.sep)), encoding="utf-8")
                    except OSError:
                        pass
                if ids:
                    for i in ids:
                        hrom_poly[i] = max(hrom_poly.get(i, 0), lv)
                hit = hrom.get(key)
                if hit:
                    for lat, lon, ra in hit:
                        points.append([lon, lat, uk, lv, 1 if ids else 0])
                else:
                    from .geo import Gazetteer, norm
                    g = Gazetteer.load()
                    gids = g.idx.get(norm(key)) or g.lookup(key)
                    if gids:
                        p = max((g.places[i] for i in gids), key=lambda q: q.pop)
                        points.append([p.lon, p.lat, uk, lv, 1 if ids else 0])
        self.oblast_levels, self.raion_levels, self.points = obl, raions, points
        self.any_obl = set(obl) | set(area_obl.values())
        self.hromada_levels = hrom_poly
        self.raions = sorted(raions)
        self.updated, self.ok, self.error = time.time(), True, None
        self.source = source

    # ---------- ukrainealarm.com (офіційне API, ключ UKRAINEALARM_API_KEY): резерв з районами й громадами
    UA_BASE = "https://api.ukrainealarm.com/api/v3"
    _ua_parent: dict | None = None

    @staticmethod
    def _ua_tree(regions, parent: str | None = None, out: dict | None = None) -> dict:
        """regionId → назва області з дерева /regions (будь-яка вкладеність regionChildIds)."""
        out = {} if out is None else out
        items = regions.get("states", []) if isinstance(regions, dict) else regions
        for r in items or []:
            name = r.get("regionName") or ""
            obl = parent or (OfficialAlerts.short(name) if r.get("regionType") == "State" else None)
            if obl:
                out[str(r.get("regionId"))] = obl
            OfficialAlerts._ua_tree(r.get("regionChildIds") or [], obl, out)
        return out

    def apply_ualarm(self, data: list, parent: dict | None = None) -> None:
        """Відповідь /alerts → ті самі рівні, що й зі зведення alerts.in.ua. Лише повітряна тривога (AIR)."""
        parent = parent or {}
        names = self._hromadas()["_oblasts"]
        obl: dict[str, int] = {}
        areas: dict[str, int] = {}
        area_obl: dict[str, str] = {}
        for r in data or []:
            if not any((a.get("type") or "").upper() == "AIR" for a in r.get("activeAlerts") or []):
                continue
            rt, name = r.get("regionType"), (r.get("regionName") or "").strip()
            o = parent.get(str(r.get("regionId")))
            if rt == "State":
                k = self.short(name)
                if k in names or k == "Київ":
                    obl[k] = 2
                continue
            if not o or o not in names:
                continue
            if rt == "District":
                uk = name.replace(" район", "").strip()
            else:  # Community / місто: «м. Харків та Харківська територіальна громада» → «м. Харків»
                uk = re.split(r"\s+та\s+", name)[0].replace(" територіальна громада", "").strip()
            areas[uk] = max(areas.get(uk, 0), 1)
            area_obl[uk] = o
        self._finish(obl, areas, area_obl, "ukrainealarm.com (офіційне API)")

    async def ualarm_once(self, cli) -> bool:
        key = config.UKRAINEALARM_KEY
        if not key:
            return False
        h = {"accept": "application/json", "authorization": key}
        try:
            if self._ua_parent is None:
                r = await cli.get(f"{self.UA_BASE}/regions", headers=h)
                r.raise_for_status()
                self._ua_parent = self._ua_tree(r.json())
            r = await cli.get(f"{self.UA_BASE}/alerts", headers=h)
            r.raise_for_status()
            self.apply_ualarm(r.json(), self._ua_parent)
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("ukrainealarm failed: %s", e)
            return False

    _H = None
    _HP = None

    @classmethod
    def hromada_ids(cls, key: str, obl: str | None, city: bool) -> list[int]:
        if cls._HP is None:
            import json
            from pathlib import Path
            d = Path(__file__).resolve().parent.parent / "data"
            try:
                fc = json.loads((d / "hromadas.geojson").read_text(encoding="utf-8"))
                ch = json.loads((d / "city_hromada.json").read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                fc, ch = {"features": []}, {}
            q = lambda x: x.replace("’", "'").replace("ʼ", "'")
            idx: dict[tuple, list[int]] = {}
            for f in fc["features"]:
                p = f["properties"]
                idx.setdefault((q(p["n"]), p["o"]), []).append(f["id"])
                idx.setdefault((q(p["n"]), q(p["r"]), p["o"]), []).append(f["id"])
            ch = {q(k): [[q(h), q(r), o] for h, r, o in v] for k, v in ch.items()}
            cls._HP = (idx, ch)
        idx, ch = cls._HP
        ap = lambda x: x.replace("’", "'").replace("ʼ", "'")
        k = ap(key.replace(" територіальна громада", "").replace(" громада", "").strip())
        out: list[int] = []
        if not city:
            out = idx.get((k, obl), []) if obl else []
        if not out:
            for h, r, o in ch.get(k, []):
                if not obl or o == obl:
                    out += idx.get((h, r, o), [])
            if len({*out}) > 1 and not obl:
                out = []  # тезки в різних областях — краще коло, ніж чужа громада
        return sorted(set(out))

    @classmethod
    def _hromadas(cls) -> dict:
        if cls._H is None:
            import json
            from pathlib import Path
            d = Path(__file__).resolve().parent.parent / "data"
            h = json.loads((d / "hromadas.json").read_text(encoding="utf-8"))
            ra = json.loads((d / "raions.geojson").read_text(encoding="utf-8"))
            ob = json.loads((d / "oblasts.geojson").read_text(encoding="utf-8"))
            h["_raions"] = {f["properties"]["n"] for f in ra["features"]}
            h["_oblasts"] = {f["properties"]["n"] for f in ob["features"]} | {"Київська", "Автономна Республіка Крим"}
            cls._H = h
        return cls._H

    async def run_open(self) -> None:
        """Без токена: відкрите зведення alerts.in.ua, резерв — ubilling (лише області)."""
        fails = 0
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "tryvoga/1.0 (civil-defence aggregator)"}) as cli:
            while True:
                try:
                    r = await cli.get(ACTIVE_MD)
                    r.raise_for_status()
                    self.apply_md(r.text)
                    if self.on_threat:
                        for ev in self.threats(r.text):
                            try:
                                self.on_threat(ev)
                            except Exception:  # noqa: BLE001
                                log.exception("threat event")
                    fails = 0
                except Exception as e:  # noqa: BLE001
                    fails += 1
                    log.warning("alerts.in.ua md failed: %s", e)
                    if fails >= 2 and not await self.ualarm_once(cli):
                        await self.ubilling_once(cli)
                await asyncio.sleep(7)  # зведення оновлюється приблизно щохвилини — ловимо зміни якнайшвидше

    async def ubilling_once(self, cli) -> None:
        try:
            r = await cli.get(UBILLING)
            r.raise_for_status()
            st = r.json().get("states", {})
            self.oblast_levels = {self.short(k): 1 for k, v in st.items() if v.get("alertnow") and k != "Севастополь"}
            self.raion_levels, self.points, self.hromada_levels = {}, [], {}
            self.updated, self.ok, self.error = time.time(), True, None
            self.source = "ubilling (лише області)"
        except Exception as e:  # noqa: BLE001
            self.ok, self.error = False, str(e)[:200]

    async def run_ubilling(self) -> None:
        """Офіційна тривога в області → жовтий; червоний ставить трекер, коли ціль уже в області."""
        self.source = "ubilling (API В. Клименка)"
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "tryvoga/1.0"}) as cli:
            while True:
                try:
                    r = await cli.get(UBILLING)
                    r.raise_for_status()
                    st = r.json().get("states", {})
                    self.oblast_levels = {self.short(k): 1 for k, v in st.items() if v.get("alertnow") and k != "Севастополь"}
                    self.updated, self.ok, self.error = time.time(), True, None
                except Exception as e:  # noqa: BLE001
                    self.ok, self.error = False, str(e)[:200]
                    log.warning("ubilling poll failed: %s", e)
                await asyncio.sleep(max(15, config.ALERTS_POLL_SEC))

    FAST_RX = re.compile(r"([А-ЯІЇЄҐ][а-яіїєґ'’ʼ]+(?:ський|цький|зький))\s+(?:район|р-н)[^\n]{0,6}?[—–-]\s*(повітряна тривога|відбій|тривога скасована)([^\n]*)", re.I)
    overrides: dict = {}
    # 04.11 власник: «у ТГ-каналах теж пишуть про початок і відбій» — міста/громади й області, не лише райони
    CITY_RX = re.compile(r"(?:^|[\s🔴🟢🟡⚠️❗️]|м\.\s*)([А-ЯІЇЄҐ][а-яіїєґ'’ʼ-]{2,})(?:\s+(?:та|і)\s+[^\n—–-]{0,40}?(?:ТГ|громада))?\s*[—–-]\s*"
                         r"(повітряна тривога|відбій(?:\s+(?:повітряної\s+)?тривоги)?|тривога скасована)(?![а-яіїєґ])", re.I)
    OBL_RX = re.compile(r"([А-ЯІЇЄҐ][а-яіїєґ'’ʼ-]+(?:ська|цька|зька))\s+(?:область|обл\.?)[^\n]{0,6}?[—–-]\s*(повітряна тривога|відбій|тривога скасована)", re.I)
    hoverrides: dict = {}
    ooverrides: dict = {}

    def fast_signal(self, text: str, ts: float) -> int:
        """Канали ретранслюють «Сумський район — повітряна тривога / відбій» раніше, ніж оновиться зведення:
        застосовуємо одразу на 2 хв, далі знову головне джерело — офіційне зведення."""
        n = 0
        names = self._hromadas()["_raions"]
        ap = lambda x: x.replace("’", "'").replace("ʼ", "'")
        for m in self.FAST_RX.finditer(text):
            nm, what, rest = m.group(1), m.group(2).lower(), m.group(3).lower()
            r = next((x for x in names if ap(x) == ap(nm)), None)
            if not r:
                continue
            lvl = 0 if what != "повітряна тривога" else (1 if "жовт" in rest else 2)
            self.overrides[r] = (lvl, ts)
            n += 1
        for m in self.OBL_RX.finditer(text):
            o = next((x for x in OBLS if ap(x) == ap(m.group(1))), None)
            if o:
                self.ooverrides[o] = (0 if m.group(2).lower() != "повітряна тривога" else 1, ts)
                n += 1
        for m in self.CITY_RX.finditer(text):
            nm, what = m.group(1), m.group(2).lower()
            if nm.endswith(("ський", "цький", "зький")) or nm.lower() in ("увага", "загроза", "тривога", "відбій"):
                continue
            ids = self.hromada_ids(nm, None, True)
            if not ids or len(ids) > 3:  # неоднозначна назва — не ризикуємо
                continue
            for i in ids:
                self.hoverrides[i] = (0 if not what.startswith("повітряна") else 1, ts)
            n += 1
        return n

    def state(self) -> dict:
        rl = dict(self.raion_levels)
        now = time.time()
        for r, (lvl, ts) in list(self.overrides.items()):
            if now - ts > 120:
                self.overrides.pop(r, None)
                continue
            if lvl:
                rl[r] = max(rl.get(r, 0), lvl)
            else:
                rl.pop(r, None)
        hl = dict(self.hromada_levels)
        for i, (lvl, ts) in list(self.hoverrides.items()):
            if now - ts > 120:
                self.hoverrides.pop(i, None)
            elif lvl:
                hl[i] = max(hl.get(i, 0), lvl)
            else:
                hl.pop(i, None)
        ol = dict(self.oblast_levels)
        for o, (lvl, ts) in list(self.ooverrides.items()):
            if now - ts > 120:
                self.ooverrides.pop(o, None)
            elif lvl:
                ol[o] = max(ol.get(o, 0), lvl)
            else:
                ol.pop(o, None)
        anyo = set(ol) | (getattr(self, "any_obl", set()) if time.time() - (self.updated or 0) < 600 else set())
        return {"levels": ol, "alert_obl": sorted(anyo), "raions": sorted(rl), "raion_levels": rl, "points": self.points, "hromadas": hl, "sep": sorted(self.sep),
                "updated": self.updated, "ok": self.ok, "error": self.error, "source": self.source}
