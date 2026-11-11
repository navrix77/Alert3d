"""Стабільний публічний API v1 для інтеграцій (сусідні проєкти).

Відокремлений від внутрішніх ендпоінтів застосунку: формат версійований і не залежить від внутрішніх полів трекера.
Доступ — за ключем (заголовок X-API-Key). Ключі: змінна PUBLIC_API_KEYS="ім'я:ключ,ім'я2:ключ2"; без неї API вимкнено (503).
Ліміт: 30 запитів/хв на ключ. Дані НЕОФІЦІЙНІ: офіційним джерелом тривог лишається система оповіщення (alerts.in.ua / «Повітряна тривога»).
"""
from __future__ import annotations

import hmac
import os
import time

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from .geo import dist_km, to_xy

router = APIRouter(prefix="/api/public/v1")
_calls: dict = {}
LIMIT, WINDOW = 30, 60
DISCLAIMER = ("Неофіційна оцінка за відкритими джерелами, може бути неповною або помилковою. "
              "Для рішень про безпеку спирайтеся на офіційні оповіщення.")
_state_fn = None


def init(state_fn) -> None:
    global _state_fn
    _state_fn = state_fn


def _keys() -> dict:
    out = {}
    for part in (os.getenv("PUBLIC_API_KEYS") or "").split(","):
        if ":" in part:
            n, k = part.split(":", 1)
            if n.strip() and len(k.strip()) >= 24:  # короткі ключі ігноруємо
                out[n.strip()] = k.strip()
    return out


def _auth(key: str | None):
    """→ (ім'я, None) або (None, відповідь-помилка)."""
    keys = _keys()
    if not keys:
        return None, JSONResponse({"error": "api_disabled"}, status_code=503)
    if key:
        for name, k in keys.items():
            if hmac.compare_digest(k.encode(), key.encode()):
                now = time.time()
                q = [x for x in _calls.get(name, []) if now - x < WINDOW]
                if len(q) >= LIMIT:
                    return None, JSONResponse({"error": "rate_limited", "retry_after": WINDOW}, status_code=429,
                                              headers={"Retry-After": str(WINDOW)})
                q.append(now)
                _calls[name] = q
                return name, None
    return None, JSONResponse({"error": "unauthorized"}, status_code=401)


def _target(t: dict, now: float) -> dict:
    return {
        "id": t["id"], "type": t["type"], "name": t["name"], "count": t.get("count"),
        "lat": round(t["lat"], 4), "lon": round(t["lon"], 4),
        "heading_deg": t.get("hd"), "speed_kmh": t.get("speed"),
        "status": t["status"],  # active | lost | closed
        "position_is_estimate": bool(t.get("pos_est")),  # true: точка розрахована, а не названа каналами
        "position_error_km": t.get("pos_km"),
        "confidence": t.get("conf"), "independent_sources": t.get("n_indep"),
        "next_place": t.get("next"), "age_s": int(max(0, now - (t.get("last") or now))),
    }


def _snapshot() -> dict:
    s = _state_fn()
    now = s["now"]
    tg = [_target(t, now) for t in s.get("tracks", []) if t.get("status") != "closed"]
    return {"v": 1, "now": int(now), "fresh": bool((s.get("fresh") or {}).get("ok", True)) if isinstance(s.get("fresh"), dict) else True,
            "alert_regions": sorted(k for k, v in (s.get("levels") or {}).items() if v),
            "targets": tg, "disclaimer": DISCLAIMER}


@router.get("/state")
def pub_state(request: Request, x_api_key: str | None = Header(default=None)):
    name, err = _auth(x_api_key)
    if err:
        return err
    return JSONResponse(_snapshot(), headers={"Cache-Control": "no-store"})


@router.get("/near")
def pub_near(lat: float, lon: float, r: float = 50, x_api_key: str | None = Header(default=None)):
    name, err = _auth(x_api_key)
    if err:
        return err
    r = max(1.0, min(r, 300.0))
    snap = _snapshot()
    H = to_xy(lat, lon)
    near = []
    for t in snap["targets"]:
        d = dist_km(H, to_xy(t["lat"], t["lon"]))
        if d <= r:
            near.append({**t, "distance_km": round(d, 1)})
    near.sort(key=lambda t: t["distance_km"])
    return JSONResponse({"v": 1, "now": snap["now"], "fresh": snap["fresh"], "radius_km": r, "targets": near,
                         "nearest_km": near[0]["distance_km"] if near else None, "disclaimer": DISCLAIMER},
                        headers={"Cache-Control": "no-store"})
