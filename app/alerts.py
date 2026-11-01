"""Офіційні тривоги (alerts.in.ua): червоний — тривога на всю область, жовтий — у частині області."""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from . import config

log = logging.getLogger("alerts")
URL = "https://api.alerts.in.ua/v1/alerts/active.json"
UBILLING = "https://ubilling.net.ua/aerialalerts/"  # без токена: стан областей (API В. Клименка)


class OfficialAlerts:
    def __init__(self) -> None:
        self.oblast_levels: dict[str, int] = {}
        self.raions: list[str] = []
        self.updated = 0.0
        self.ok = False
        self.error: str | None = None

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
            await self.run_ubilling()
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
        return {"levels": self.oblast_levels, "raions": self.raions, "updated": self.updated, "ok": self.ok, "error": self.error}
