"""Відкриті джерела замість DeepState (без дозволу DeepState їхні дані не беремо).

1) Зона контролю: будь-який публічний ArcGIS FeatureServer (напр. шар ISW/CTP) — адреса у змінній FRONT_URL
   (повний URL шару до «/query», без параметрів). Умови шару й атрибуцію перевіряє власник: FRONT_ATTR.
2) Аеродроми ворога: OpenStreetMap через Overpass (ODbL; атрибуція «© OpenStreetMap contributors»).
Обидва вимкнені, поки не задано змінні; файли пишуться у ті самі data/occupied.geojson та data/enemy_objects.geojson.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import httpx

log = logging.getLogger("open_front")
DATA = Path(__file__).resolve().parent.parent / "data"
OUT, OBJ = DATA / "occupied.geojson", DATA / "enemy_objects.geojson"
OVERPASS = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
# (пд, зх, пн, сх): Крим, окупований південь/схід, Білорусь, західна Росія — поза Україною лише те, що ближче 600 км
AF_BOXES = ("44.3,32.4,46.2,36.7", "46.0,33.0,48.5,40.3", "51.2,23.2,56.2,32.8", "50.0,34.0,56.0,42.0")


def poly_extract(doc: dict, attr: str = "") -> dict:
    feats = []
    for f in doc.get("features", []):
        g = f.get("geometry") or {}
        if g.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        def strip(c):
            return [strip(x) for x in c] if isinstance(c[0], list) else [round(c[0], 5), round(c[1], 5)]
        feats.append({"type": "Feature", "properties": {"k": "occupied"}, "geometry": {"type": g["type"], "coordinates": strip(g["coordinates"])}})
    return {"type": "FeatureCollection", "features": feats,
            "properties": {"source": attr or "open ArcGIS", "fetched": int(time.time()), "v": 2}}


def af_extract(doc: dict) -> dict:
    feats, seen = [], set()
    for e in doc.get("elements", []):
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lon = e.get("lon") or (e.get("center") or {}).get("lon")
        if lat is None or lon is None or (e.get("type"), e.get("id")) in seen:
            continue
        seen.add((e.get("type"), e.get("id")))
        t = e.get("tags") or {}
        name = t.get("name:uk") or t.get("name") or t.get("name:en") or "Аеродром"
        feats.append({"type": "Feature", "properties": {"n": name[:80], "d": "OpenStreetMap", "c": "airfield"},
                      "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]}})
    return {"type": "FeatureCollection", "features": feats,
            "properties": {"source": "© OpenStreetMap contributors (ODbL)", "fetched": int(time.time()), "v": 1}}


def af_query() -> str:
    parts = "".join(f'nwr["military"="airfield"]({b});' for b in AF_BOXES)
    return f"[out:json][timeout:60];({parts});out center;"


async def _stale(p: Path, hours: int = 12) -> bool:
    return not p.exists() or time.time() - p.stat().st_mtime > hours * 3600


async def run() -> None:
    front, attr = os.environ.get("FRONT_URL", "").strip(), os.environ.get("FRONT_ATTR", "")
    airf = os.environ.get("OSM_AIRFIELDS", "1") == "1"
    if not front and not airf:
        return
    async with httpx.AsyncClient(timeout=70, headers={"User-Agent": "navryx-sky/1.0 (civil air-alert aggregator)"}) as cli:
        while True:
            if front and await _stale(OUT):
                try:
                    r = await cli.get(front.rstrip("/") + "/query", params={"where": "1=1", "outFields": "*", "outSR": 4326, "f": "geojson"})
                    r.raise_for_status()
                    fc = poly_extract(r.json(), attr)
                    if fc["features"]:
                        OUT.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
                        log.info("зона контролю: %d полігонів (%s)", len(fc["features"]), attr)
                except Exception as e:  # noqa: BLE001
                    log.warning("FRONT_URL: %s", e)
            if airf and await _stale(OBJ, 24 * 7):
                try:
                    r = await cli.post(OVERPASS, data={"data": af_query()})
                    r.raise_for_status()
                    fc = af_extract(r.json())
                    if fc["features"]:
                        OBJ.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
                        log.info("OSM аеродроми: %d", len(fc["features"]))
                except Exception as e:  # noqa: BLE001
                    log.warning("Overpass: %s", e)
            await asyncio.sleep(3600)
