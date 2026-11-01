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
        coords = strip(g["coordinates"])
        ring = coords[0] if g["type"] == "Polygon" else coords[0][0]
        clon = sum(p[0] for p in ring) / len(ring)
        clat = sum(p[1] for p in ring) / len(ring)
        if not (22 <= clon <= 40.5 and 44 <= clat <= 52.5):
            continue  # лише Україна (відкидаємо Грузію, Молдову тощо, хоч би як вони були підписані)
        feats.append({"type": "Feature", "properties": {"k": kind}, "geometry": {"type": g["type"], "coordinates": coords}})
    return {"type": "FeatureCollection", "features": feats, "properties": {"source": "DeepStateMap", "date": doc.get("datetime"), "fetched": int(time.time()), "v": 2}}


async def run() -> None:
    async with httpx.AsyncClient(timeout=40, headers={"User-Agent": "tryvoga/1.0 (civil-defence aggregator)"}) as cli:
        while True:
            fresh = False
            if OUT.exists() and time.time() - OUT.stat().st_mtime < 12 * 3600:
                try:
                    fresh = json.loads(OUT.read_text(encoding="utf-8")).get("properties", {}).get("v") == 2
                except Exception:  # noqa: BLE001
                    fresh = False
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
