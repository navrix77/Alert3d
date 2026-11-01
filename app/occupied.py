"""Тимчасово окуповані території — щодня з DeepStateMap (deepstatemap.live).

Беремо лише полігони України: «Окуповано», ОРДЛО, окупований Крим, Тузла, і окремо «Статус невідомий» (сіра зона).
Придністров'я та інші країни відкидаємо. Файл зберігається локально — карта працює, навіть якщо DeepState недоступний.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import httpx

log = logging.getLogger("occupied")
URL = "https://deepstatemap.live/api/history/last"
OUT = Path(__file__).resolve().parent.parent / "data" / "occupied.geojson"
FOREIGN = ("придністров", "transnistria", "цхінвал", "абхаз", "tskhinvali", "abkhaz")


def extract(doc: dict) -> dict:
    feats = []
    for f in (doc.get("map") or doc).get("features", []):
        g = f.get("geometry") or {}
        if g.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        name = str((f.get("properties") or {}).get("name", ""))
        low = name.lower()
        if any(x in low for x in FOREIGN):
            continue
        if "окуп" in low or "ордло" in low or "occupied" in low:
            kind = "occupied"
        elif "невідом" in low or "unknown" in low:
            kind = "unknown"
        else:
            continue
        # DeepState пише координати як [lon, lat, 0] — третю складову прибираємо
        def strip(c):
            return [strip(x) for x in c] if isinstance(c[0], list) else c[:2]
        feats.append({"type": "Feature", "properties": {"k": kind}, "geometry": {"type": g["type"], "coordinates": strip(g["coordinates"])}})
    return {"type": "FeatureCollection", "features": feats, "properties": {"source": "DeepStateMap", "date": doc.get("datetime"), "fetched": int(time.time())}}


async def run() -> None:
    async with httpx.AsyncClient(timeout=40, headers={"User-Agent": "tryvoga/1.0 (civil-defence aggregator)"}) as cli:
        while True:
            fresh = OUT.exists() and time.time() - OUT.stat().st_mtime < 12 * 3600
            if not fresh:
                try:
                    r = await cli.get(URL)
                    r.raise_for_status()
                    fc = extract(r.json())
                    if fc["features"]:
                        OUT.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
                        log.info("DeepState: %d полігонів окупації/сірої зони (%s)", len(fc["features"]), fc["properties"]["date"])
                except Exception as e:  # noqa: BLE001
                    log.warning("DeepState недоступний: %s", e)
            await asyncio.sleep(3600)
