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
        feats.append({"type": "Feature", "properties": {"n": name[:80], "d": "OpenStreetMap", "c": MIL_TAGS.get((t.get("military") or ""), "object")},
                      "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]}})
    return {"type": "FeatureCollection", "features": feats,
            "properties": {"source": "© OpenStreetMap contributors (ODbL)", "fetched": int(time.time()), "v": 1}}


MIL_TAGS = {"airfield": "airfield", "naval_base": "naval", "base": "object", "barracks": "object", "depot": "depot", "ammunition": "depot"}
WD_URL = os.environ.get("WIKIDATA_URL", "https://query.wikidata.org/sparql")


def af_query() -> str:
    parts = "".join(f'nwr["military"~"^({"|".join(MIL_TAGS)})$"]({b});' for b in AF_BOXES)
    return f"[out:json][timeout:90];({parts});out center;"


def wd_query() -> str:
    boxes = " UNION ".join(
        f'{{ SERVICE wikibase:box {{ ?item wdt:P625 ?c . bd:serviceParam wikibase:cornerSouthWest "Point({b.split(",")[1]} {b.split(",")[0]})"^^geo:wktLiteral . bd:serviceParam wikibase:cornerNorthEast "Point({b.split(",")[3]} {b.split(",")[2]})"^^geo:wktLiteral }} }}'
        for b in AF_BOXES)
    return ("SELECT ?item ?itemLabel ?c ?cls WHERE { VALUES ?cls { wd:Q695850 wd:Q245016 wd:Q1062669 } ?item wdt:P31/wdt:P279* ?cls . "
            + boxes + ' SERVICE wikibase:label { bd:serviceParam wikibase:language "uk,en". } } LIMIT 3000')


def wd_extract(doc: dict) -> list[dict]:
    out = []
    for b in (doc.get("results") or {}).get("bindings", []):
        w = (b.get("c") or {}).get("value", "")
        if not w.startswith("Point("):
            continue
        try:
            lon, lat = (float(x) for x in w[6:-1].split())
        except ValueError:
            continue
        cls = (b.get("cls") or {}).get("value", "")
        out.append({"type": "Feature", "properties": {"n": ((b.get("itemLabel") or {}).get("value") or "Об'єкт")[:80], "d": "Wikidata",
                    "c": "airfield" if cls.endswith("Q695850") else "object"},
                    "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]}})
    return out


def merge(osm: dict, wd: list[dict], km: float = 2.0) -> dict:
    import math
    def far(a, b):
        dx = (a[0] - b[0]) * 111.3 * math.cos(math.radians(a[1])); dy = (a[1] - b[1]) * 111.3
        return math.hypot(dx, dy) > km
    feats = list(osm["features"])
    for f in wd:
        if all(far(f["geometry"]["coordinates"], g["geometry"]["coordinates"]) for g in feats):
            feats.append(f)
    osm = dict(osm)
    osm["features"] = feats
    osm["properties"] = {**osm["properties"], "source": "© OpenStreetMap contributors (ODbL); Wikidata (CC0)"}
    return osm


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
                    try:
                        w = await cli.get(WD_URL, params={"query": wd_query(), "format": "json"})
                        w.raise_for_status()
                        fc = merge(fc, wd_extract(w.json()))
                    except Exception as e:  # noqa: BLE001
                        log.warning("Wikidata: %s", e)
                    if fc["features"]:
                        OBJ.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
                        log.info("OSM аеродроми: %d", len(fc["features"]))
                except Exception as e:  # noqa: BLE001
                    log.warning("Overpass: %s", e)
            await asyncio.sleep(3600)
