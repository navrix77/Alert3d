"""ТІЛЬКИ ДЛЯ ТЕСТУ, вимкнено за замовчуванням (DEEPSTATE_ARCHIVE=1).

Щоденний архів полігонів окупації DeepStateMap у GitHub-репозиторії cyterat/deepstate-map-data (GPL-3.0 стосується скриптів архіву).
Дані належать DeepStateMap, чиї умови забороняють передавати їх третім особам без дозволу: тому НЕ вмикати на публічному сайті,
доки DeepState не відповість на заявку. Атрибуція в самому шарі лишається «DeepStateMap».
Коли ввімкнено, VIINA (app/viina.py) цей файл не перезаписує.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

log = logging.getLogger("ds_archive")
OUT = Path(__file__).resolve().parent.parent / "data" / "occupied.geojson"
RAW = "https://raw.githubusercontent.com/cyterat/deepstate-map-data/main/data/deepstatemap_data_{d}.geojson"
ENABLED = lambda: os.environ.get("DEEPSTATE_ARCHIVE") == "1"  # noqa: E731


def extract(doc: dict, day: str) -> dict:
    feats = []
    for f in doc.get("features", []):
        g = f.get("geometry") or {}
        if g.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        def rnd(c):
            return [rnd(x) for x in c] if isinstance(c[0], list) else [round(c[0], 5), round(c[1], 5)]
        feats.append({"type": "Feature", "properties": {"k": "occupied"}, "geometry": {"type": g["type"], "coordinates": rnd(g["coordinates"])}})
    return {"type": "FeatureCollection", "features": feats,
            "properties": {"source": "DeepStateMap (архів cyterat/deepstate-map-data), тест", "date": day, "fetched": int(time.time()), "v": 2}}


async def run() -> None:
    if not ENABLED():
        return
    log.warning("DEEPSTATE_ARCHIVE=1: дані DeepState через архів, лише для тесту")
    async with httpx.AsyncClient(timeout=60, follow_redirects=True, headers={"User-Agent": "navryx-sky-test/1.0"}) as cli:
        while True:
            try:
                if not OUT.exists() or time.time() - OUT.stat().st_mtime > 6 * 3600 or "архів" not in OUT.read_text(encoding="utf-8")[:300]:
                    for back in range(0, 6):
                        d = (date.today() - timedelta(days=back)).strftime("%Y%m%d")
                        r = await cli.get(RAW.format(d=d))
                        if r.status_code == 200:
                            fc = extract(r.json(), d)
                            if fc["features"]:
                                OUT.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
                                log.info("DeepState-архів: %s", d)
                            break
            except Exception as e:  # noqa: BLE001
                log.warning("DeepState-архів: %s", e)
            await asyncio.sleep(3600)
