"""Самонавчання словника місць (08.11): слова, які бот не впізнав у постах (audit no_place), щоночі геокодуються й потрапляють у
data/learned_places.json; parser підхоплює файл на льоту. Обережно: кандидат — лише слово з ≥2 різних постів, знайдене в межах свого міста,
з назвою, схожою на слово з посту. Негативні відповіді кешуються, щоб не бити сервіс повторно.

    python -m app.dictlearn            # одна нічна ітерація
"""
from __future__ import annotations

import collections
import json
import logging
import math
import os
import re
import time
from pathlib import Path

log = logging.getLogger("dictlearn")
DIR = Path(os.getenv("PERSIST_DIR") or Path(__file__).resolve().parent.parent / "data")
LEARNED = DIR / "learned_places.json"
NEG = DIR / "learned_negative.json"
AUDIT = DIR / "audit.jsonl"
UA = {"User-Agent": "NavryxSky-dictlearn/1.0 (air-alert aggregator; contact via repo navrix77/Alert3d)"}
# область каналу → (місто, центр, радіус км допустимого пошуку)
CITY = {
    "Харківська": ("Харків", 49.99, 36.23, 22), "Київ": ("Київ", 50.45, 30.52, 30), "Київська": ("Київ", 50.45, 30.52, 30),
    "Запорізька": ("Запоріжжя", 47.84, 35.14, 22), "Дніпропетровська": ("Дніпро", 48.46, 35.04, 22), "Одеська": ("Одеса", 46.48, 30.73, 22),
    "Сумська": ("Суми", 50.91, 34.80, 15), "Миколаївська": ("Миколаїв", 46.97, 32.00, 15), "Херсонська": ("Херсон", 46.64, 32.61, 15),
    "Чернігівська": ("Чернігів", 51.50, 31.30, 15), "Полтавська": ("Полтава", 49.59, 34.55, 15), "Львівська": ("Львів", 49.84, 24.03, 18),
}
STOP = {"Курсом", "Курс", "Ударний", "Ударный", "Балістика", "Група", "Групи", "Нова", "Новий", "Нові", "Реактивний", "Дрон", "Шахед", "Увага", "Просто"}
MIN_POSTS = 2
MAX_PER_RUN = 25


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def candidates(rows: list[dict]) -> list[tuple[str, str, int]]:
    """(слово, область каналу, кількість різних постів) із записів no_place."""
    from .config import CHANNEL_REGION
    posts: dict[tuple[str, str], set] = collections.defaultdict(set)
    for r in rows:
        if r.get("kind") != "no_place":
            continue
        w = (r.get("place") or "").strip()
        reg = CHANNEL_REGION.get(r.get("src") or "") or ""
        if not w or w == "?" or w in STOP or reg not in CITY or len(w) < 4:
            continue
        posts[(w, reg)].add((r.get("text") or "")[:80] or r.get("t"))
    return sorted(((w, reg, len(v)) for (w, reg), v in posts.items() if len(v) >= MIN_POSTS), key=lambda x: -x[2])


def _km(a, b) -> float:
    return math.hypot((a[0] - b[0]) * 111, (a[1] - b[1]) * 111 * math.cos(math.radians(a[0])))


def stem_rx(word: str) -> str:
    """Закінчення відмінюються («Дафі», «Ужвій»): беремо основу без 1–2 останніх літер, але не коротше 4."""
    w = re.sub(r"[^а-яіїєґ'’\-]", "", word.lower())
    cut = max(4, len(w) - 2)
    return re.escape(w[:cut]).replace("'", "['’]")


def geocode(word: str, city: str, lat: float, lon: float, rad: float):
    """Nominatim (OSM) у межах міста; повертає (назва, lat, lon) або None. Не більш як 1 запит/с — ліміт сервісу."""
    import httpx
    d = rad / 111.0
    p = {"q": f"{word}, {city}", "format": "jsonv2", "limit": 3, "accept-language": "uk", "countrycodes": "ua",
         "viewbox": f"{lon - d * 1.5},{lat + d},{lon + d * 1.5},{lat - d}", "bounded": 1}
    try:
        r = httpx.get("https://nominatim.openstreetmap.org/search", params=p, headers=UA, timeout=15)
        r.raise_for_status()
        res = r.json()
    except Exception as e:  # noqa: BLE001
        log.warning("geocode %s: %s", word, e)
        return "ERR"
    pref = word.lower()[:4]
    for it in res:
        nm = (it.get("name") or it.get("display_name", "").split(",")[0]).strip()
        la, lo = float(it["lat"]), float(it["lon"])
        if nm and nm.lower().replace("тц", "")[:1] is not None and (pref in nm.lower() or nm.lower()[:3] == pref[:3]) and _km((lat, lon), (la, lo)) <= rad:
            return nm, la, lo
    return None


def run(rows: list[dict] | None = None, geo=geocode, sleep=1.1) -> dict:
    rows = rows if rows is not None else _read_audit()
    learned = _load(LEARNED, [])
    neg = _load(NEG, {})
    have = {e["rx"] for e in learned}
    added, tried = [], 0
    for w, reg, n in candidates(rows):
        city, la, lo, rad = CITY[reg]
        rx = stem_rx(w)
        if rx in have or neg.get(f"{rx}|{city}", 0) > time.time() - 7 * 86400 or tried >= MAX_PER_RUN:
            continue
        tried += 1
        res = geo(w, city, la, lo, rad)
        if sleep:
            time.sleep(sleep)
        if res == "ERR":
            break  # мережа/ліміт: до наступної ночі
        if not res:
            neg[f"{rx}|{city}"] = int(time.time())
            continue
        nm, pla, plo = res
        e = {"rx": rx, "name": f"{nm} ({city})", "lat": round(pla, 5), "lon": round(plo, 5), "n": n, "word": w, "t": int(time.time())}
        learned.append(e)
        have.add(rx)
        added.append(e)
    if added:
        LEARNED.write_text(json.dumps(learned, ensure_ascii=False, indent=1), encoding="utf-8")
    NEG.write_text(json.dumps(neg, ensure_ascii=False), encoding="utf-8")
    return {"tried": tried, "added": [e["name"] for e in added], "total": len(learned)}


def _read_audit() -> list[dict]:
    rows = []
    for f in (AUDIT.with_suffix(".1.jsonl"), AUDIT):
        try:
            for ln in f.read_text(encoding="utf-8").splitlines():
                try:
                    rows.append(json.loads(ln))
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
    return rows


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run())
