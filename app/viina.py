"""Зона контролю з VIINA 2.0 (zhukovyuri/VIINA, ліцензія ODbL, атрибуція обов'язкова).

Береться щоденний статус контролю кожного населеного пункту (UA / RU / CONTESTED) і полігони населених пунктів (GeoNames).
Голос DeepState у VIINA («status_dsm») НЕ використовуємо: беремо `status_boost` (Вікіпедія + події VIINA), а якщо його немає, `status_wiki`.
RU стає «окуповано», CONTESTED сірою зоною («статус невідомий»). Це рівень населених пунктів, а не точна лінія фронту.
Файли пишуться в data/occupied.geojson (той самий, що читає мапа). Вимкнути: VIINA=0.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import time
import zipfile
from datetime import date
from pathlib import Path

import httpx

log = logging.getLogger("viina")
DATA = Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "occupied.geojson"
TESS = DATA / "viina_gn_tess.geojson"
RAW = "https://github.com/zhukovyuri/VIINA/raw/master/Data/"
ATTR = "VIINA 2.0 (zhukovyuri/VIINA), ODbL"
KIND = {"RU": "occupied", "CONTESTED": "unknown"}


def latest_status(zbytes: bytes) -> tuple[str, dict[int, str]]:
    """Останній день у CSV всередині zip → {geonameid: статус}. Читаємо потоково (файл на рік великий)."""
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(name) as fh:
            rd = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", newline=""))
            best, rows = "", {}
            for r in rd:
                d = (r.get("date") or "").strip()
                if not d or d < best:
                    continue
                if d > best:
                    best, rows = d, {}
                st = (r.get("status_boost") or r.get("status_wiki") or "").strip().upper()
                try:
                    rows[int(float(r["geonameid"]))] = st
                except (KeyError, ValueError):
                    continue
    return best, rows


def build(tess: dict, status: dict[int, str], day: str) -> dict:
    from shapely.geometry import shape, mapping
    from shapely.ops import unary_union

    groups: dict[str, list] = {"occupied": [], "unknown": []}
    for f in tess.get("features", []):
        try:
            gid = int(float(f["properties"]["geonameid"]))
        except (KeyError, TypeError, ValueError):
            continue
        k = KIND.get(status.get(gid, ""))
        if k:
            groups[k].append(shape(f["geometry"]).buffer(0))
    feats = []
    for k, geoms in groups.items():
        if not geoms:
            continue
        u = unary_union(geoms).simplify(0.004, preserve_topology=True)
        for g in (u.geoms if hasattr(u, "geoms") else [u]):
            if g.is_empty or g.area < 1e-5:
                continue
            m = mapping(g)
            def rnd(c):
                return [rnd(x) for x in c] if isinstance(c[0], (list, tuple)) else [round(c[0], 4), round(c[1], 4)]
            feats.append({"type": "Feature", "properties": {"k": k}, "geometry": {"type": m["type"], "coordinates": rnd(m["coordinates"])}})
    return {"type": "FeatureCollection", "features": feats,
            "properties": {"source": ATTR, "date": day, "fetched": int(time.time()), "v": 2}}


async def run() -> None:
    if os.environ.get("VIINA", "1") != "1":
        return
    async with httpx.AsyncClient(timeout=300, follow_redirects=True, headers={"User-Agent": "navryx-sky/1.0 (civil air-alert aggregator)"}) as cli:
        while True:
            try:
                if not OUT.exists() or time.time() - OUT.stat().st_mtime > 20 * 3600 or "VIINA" not in OUT.read_text(encoding="utf-8")[:400]:
                    if not TESS.exists():
                        r = await cli.get(RAW + "gn_UA_tess.geojson")
                        r.raise_for_status()
                        TESS.write_bytes(r.content)
                    r = await cli.get(RAW + f"control_latest_{date.today().year}.zip")
                    r.raise_for_status()
                    day, st = await asyncio.to_thread(latest_status, r.content)
                    tess = json.loads(TESS.read_text(encoding="utf-8"))
                    fc = await asyncio.to_thread(build, tess, st, day)
                    if fc["features"]:
                        OUT.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
                        log.info("VIINA: %d полігонів контролю станом на %s", len(fc["features"]), day)
            except Exception as e:  # noqa: BLE001
                log.warning("VIINA: %s", e)
            await asyncio.sleep(3600)
