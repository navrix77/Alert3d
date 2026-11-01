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


class OfficialAlerts:
    def __init__(self) -> None:
        self.oblast_levels: dict[str, int] = {}
        self.raions: list[str] = []
        self.updated = 0.0
        self.ok = False
        self.error: str | None = None
        self.raion_levels: dict[str, int] = {}
        self.points: list[list] = []
        self.source = ""

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
                await asyncio.sleep(config.ALERTS_POLL_SEC)

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
        hrom = self._hromadas()
        for m in self.LINE.finditer(sec):
            name, rest = m.group(1).strip(), m.group(2)
            if name not in hrom["_oblasts"]:
                continue  # області РФ теж є у зведенні — пропускаємо
            if "areas affected" not in rest:
                obl[name] = 2 if re.search(r"level:\s*red|\[red", rest) else 1
                continue
            got = self.parse_areas(rest)
            if not got:  # формат знову змінився — краще залити всю область, ніж пропустити тривогу
                obl[name] = 2 if "red" in rest else 1
                log.warning("alerts.in.ua: не розібрав райони для %s", name)
            for uk, lv in got:
                areas[uk] = max(areas.get(uk, 0), lv)
        raions: dict[str, int] = {}
        points: list[list] = []
        ap = lambda x: x.replace("’", "'").replace("ʼ", "'")
        rmap = {ap(r): r for r in hrom["_raions"]}
        for uk, lv in areas.items():
            if ap(uk) in rmap and uk.endswith(("ський", "цький", "зький", "ний")):
                r = rmap[ap(uk)]
                raions[r] = max(raions.get(r, 0), lv)
            else:
                key = uk.replace("м. ", "").strip()
                hit = hrom.get(key)
                if hit:
                    for lat, lon, ra in hit:
                        points.append([lon, lat, uk, lv])
                else:
                    from .geo import Gazetteer, norm
                    g = Gazetteer.load()
                    ids = g.idx.get(norm(key)) or g.lookup(key)
                    if ids:
                        p = max((g.places[i] for i in ids), key=lambda q: q.pop)
                        points.append([p.lon, p.lat, uk, lv])
        self.oblast_levels, self.raion_levels, self.points = obl, raions, points
        self.raions = sorted(raions)
        self.updated, self.ok, self.error = time.time(), True, None
        self.source = "alerts.in.ua (відкрите зведення)"

    _H = None

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
                    fails = 0
                except Exception as e:  # noqa: BLE001
                    fails += 1
                    log.warning("alerts.in.ua md failed: %s", e)
                    if fails >= 2:
                        await self.ubilling_once(cli)
                await asyncio.sleep(20)

    async def ubilling_once(self, cli) -> None:
        try:
            r = await cli.get(UBILLING)
            r.raise_for_status()
            st = r.json().get("states", {})
            self.oblast_levels = {self.short(k): 1 for k, v in st.items() if v.get("alertnow") and k != "Севастополь"}
            self.raion_levels, self.points = {}, []
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

    def state(self) -> dict:
        return {"levels": self.oblast_levels, "raions": self.raions, "raion_levels": self.raion_levels, "points": self.points,
                "updated": self.updated, "ok": self.ok, "error": self.error, "source": self.source}
