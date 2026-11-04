"""Тимчасово окуповані території — щодня з DeepStateMap (deepstatemap.live).

Беремо лише полігони України: «Окуповано», ОРДЛО, окупований Крим, Тузла, і окремо «Статус невідомий» (сіра зона).
Придністров'я та інші країни відкидаємо. Файл зберігається локально — карта працює, навіть якщо DeepState недоступний.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import logging
import time
from pathlib import Path

import httpx

log = logging.getLogger("occupied")
URL = "https://deepstatemap.live/api/history/last"
OUT = Path(__file__).resolve().parent.parent / "data" / "occupied.geojson"
OBJ = Path(__file__).resolve().parent.parent / "data" / "enemy_objects.geojson"
SUMMARY = Path(__file__).resolve().parent.parent / "data" / "enemy_summary.json"
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


# Категорії точкових об'єктів ворога за назвою (структура даних DeepState перевіряється за enemy_summary.json після першого завантаження)
CATS = (("airfield", re.compile(r"аеродром|airfield|air ?base|авіабаз|аэродром", re.I)),
        ("hq", re.compile(r"штаб|\bhq\b|headquarter|командн", re.I)),
        ("depot", re.compile(r"склад|депо\b|arsenal|depot|арсенал|база зберіг", re.I)),
        ("naval", re.compile(r"флот|naval|порт\b|корабл|військово-морськ", re.I)),
        ("air_def", re.compile(r"ппо|с-300|с-400|air defen|зрк|sam\b", re.I)))


def objects(doc: dict) -> tuple[dict, dict]:
    """Точкові позначки DeepState (не полігони): розміщення об'єктів ворога. Назву беремо до «//», решту опису лишаємо як є."""
    feats, names, geoms = [], {}, {}
    for f in (doc.get("map") or doc).get("features", []):
        g = f.get("geometry") or {}
        geoms[g.get("type")] = geoms.get(g.get("type"), 0) + 1
        if g.get("type") != "Point":
            continue
        pr = f.get("properties") or {}
        name = str(pr.get("name", "")).strip()
        lon, lat = g["coordinates"][:2]
        if not (22 <= lon <= 40.5 and 44 <= lat <= 52.5):
            continue
        short = name.split("//")[0].strip() or name
        cat = next((k for k, rx in CATS if rx.search(name)), "object")
        names[short] = names.get(short, 0) + 1
        feats.append({"type": "Feature", "properties": {"n": short[:80], "d": str(pr.get("description", ""))[:240], "c": cat},
                      "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]}})
    fc = {"type": "FeatureCollection", "features": feats, "properties": {"source": "DeepStateMap", "date": doc.get("datetime"), "fetched": int(time.time()), "v": 1}}
    summ = {"date": doc.get("datetime"), "fetched": int(time.time()), "geometry_types": geoms, "points_in_ukraine": len(feats),
            "categories": {c: sum(1 for x in feats if x["properties"]["c"] == c) for c in ("airfield", "hq", "depot", "naval", "air_def", "object")},
            "top_names": sorted(names.items(), key=lambda kv: -kv[1])[:60]}
    return fc, summ


async def run() -> None:
    if os.environ.get("DEEPSTATE_TERRITORY") != "1":
        log.info("DeepState вимкнено (немає дозволу); джерела — app/open_front.py")
        return
    async with httpx.AsyncClient(timeout=40, headers={"User-Agent": "tryvoga/1.0 (civil-defence aggregator)"}) as cli:
        while True:
            fresh = False
            if OUT.exists() and time.time() - OUT.stat().st_mtime < 12 * 3600:
                try:
                    fresh = json.loads(OUT.read_text(encoding="utf-8")).get("properties", {}).get("v") == 2 and (OBJ.exists() or os.environ.get("DEEPSTATE_OBJECTS") != "1")
                except Exception:  # noqa: BLE001
                    fresh = False
            if not fresh:
                try:
                    r = await cli.get(URL)
                    r.raise_for_status()
                    doc = r.json()
                    fc = extract(doc)
                    try:
                        if os.environ.get("DEEPSTATE_OBJECTS") != "1":
                            raise RuntimeError("точкові об'єкти DeepState вимкнено: потрібен письмовий дозвіл на показ (api.deepstatemap.live/request)")
                        ofc, summ = objects(doc)
                        OBJ.write_text(json.dumps(ofc, ensure_ascii=False), encoding="utf-8")
                        SUMMARY.write_text(json.dumps(summ, ensure_ascii=False), encoding="utf-8")
                        log.info("DeepState: %d точкових об'єктів (%s)", len(ofc["features"]), summ["categories"])
                    except Exception as e:  # noqa: BLE001
                        log.warning("DeepState об'єкти: %s", e)
                    if fc["features"]:
                        OUT.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
                        log.info("DeepState: %d полігонів окупації/сірої зони (%s)", len(fc["features"]), fc["properties"]["date"])
                except Exception as e:  # noqa: BLE001
                    log.warning("DeepState недоступний: %s", e)
            await asyncio.sleep(3600)
