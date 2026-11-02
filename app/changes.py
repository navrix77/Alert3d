"""«Що змінилося, поки мене не було?» — короткий огляд змін для обраного місця за проміжок.

Будується з того, що SKY уже має: щохвилинні кадри (що було відомо тоді), поточний стан і докази цілей
(першоджерела, перепости, хто змінив курс). Кожен рядок — подія з часом, джерелом і точками «було → стало»,
щоб мапа могла програти саме ці зміни.

Категорії подій:
  official — тривогу в області/районі місця оголошено або знято;
  new      — нова ціль поруч або з курсом на місце; скільки незалежних джерел і скільки перепостів;
  course   — курс уточнено (було → A, тепер → B), хто і коли це написав;
  closer / away — ціль помітно наблизилась / віддаляється;
  lost     — про ціль, що була поруч, канали замовкли (це НЕ відбій);
  closed   — канали написали «збито / не фіксується».
"""
from __future__ import annotations

import math

from .geo import bearing, dist_km, to_xy

FROM = ["півночі", "північного сходу", "сходу", "південного сходу", "півдня", "південного заходу", "заходу", "північного заходу"]


def _side(H, P) -> str:
    return FROM[round(bearing(H, P) / 45) % 8]


def _toward(t: dict, H, P) -> bool:
    hd = t.get("hd")
    if hd is None:
        return False
    d = abs((bearing(P, H) - hd + 540) % 360 - 180)
    return d <= 30


def _relevant(t: dict, H, r_km: float) -> tuple[bool, float]:
    P = to_xy(t["lat"], t["lon"])
    d = dist_km(H, P)
    return (d <= r_km or (d <= 2.5 * r_km and _toward(t, H, P))), d


def frame_at(frames: list[dict], since: float) -> dict | None:
    """Останній кадр не пізніше since (що було відомо тоді)."""
    best = None
    for f in frames:
        if f["t"] <= since + 30:
            best = f
        else:
            break
    return best


def changes(frames: list[dict], now_snap: dict, lon: float, lat: float, since: float, r_km: float = 60,
            names: dict | None = None, ev_of=None, obl: str | None = None, raion: str | None = None) -> dict:
    """frames — кадри машини часу; now_snap — поточний стан; ev_of(id) — повні докази цілі (items)."""
    names = names or {}
    H = to_xy(lat, lon)
    now = now_snap.get("now") or 0
    then = frame_at(frames, since)
    ev: list[dict] = []

    # --- офіційний статус місця
    def lv(levels: dict | None, raions: dict | None) -> int:
        a = (levels or {}).get(obl, 0) if obl else 0
        b = (raions or {}).get(raion, 0) if raion else 0
        return 1 if (a or b) else 0
    off_now = lv(now_snap.get("levels"), (now_snap.get("official") or {}).get("raion_levels"))
    if then is not None:
        off_then = lv(then.get("levels"), then.get("raions"))
        if off_then != off_now:
            # момент зміни — перший кадр із новим статусом
            tchg = next((f["t"] for f in frames if f["t"] > then["t"] and lv(f.get("levels"), f.get("raions")) == off_now), now)
            ev.append({"k": "official", "t": tchg, "on": off_now,
                       "text": ("Оголошено повітряну тривогу" if off_now else "Офіційний відбій тривоги") + (f" ({raion} р-н)" if raion and not (now_snap.get('levels') or {}).get(obl) and off_now else "")})
    then_tr = {t["id"]: t for t in (then or {}).get("tracks", [])}
    now_tr = {t["id"]: t for t in now_snap.get("tracks", [])}

    for tid, t in now_tr.items():
        st = t.get("status")
        rel, d = _relevant(t, H, r_km)
        old = then_tr.get(tid)
        typ = names.get(t["type"], t["type"])
        P = to_xy(t["lat"], t["lon"])
        if st == "active" and rel and old is None and (t.get("first") or now) >= since - 60:
            e = t.get("ev") or {}
            pubs, indep = e.get("pubs", 1), e.get("indep", 1)
            rep = max(0, pubs - indep)
            src = (e.get("prim") or [None])[0]
            ev.append({"k": "new", "t": t.get("first") or now, "id": tid, "type": t["type"], "to": [t["lon"], t["lat"]],
                       "text": f"Нова ціль: {typ}" + (f" ×{t['count']}" if (t.get('count') or 1) > 1 else "") + f", {round(d)} км з {_side(H, P)}"
                               + (f", курс → {t['next']}" if t.get("next") else "")
                               + (f". Незалежних джерел: {indep}" if indep > 1 else ". Одне першоджерело") + (f", повторили ще {rep} канал(и)" if rep else ""),
                       "src": src, "conf": t.get("conf")})
            continue
        if old is None:
            continue
        rel_old, d_old = _relevant(old, H, r_km)
        if not (rel or rel_old):
            continue
        if st == "closed":
            ev.append({"k": "closed", "t": t.get("last") or now, "id": tid, "type": t["type"], "from": [old["lon"], old["lat"]],
                       "text": f"{typ} ({round(d_old)} км з {_side(H, to_xy(old['lat'], old['lon']))}) — канали написали «збито / не фіксується»"})
            continue
        if st == "lost":
            ev.append({"k": "lost", "t": t.get("last") or now, "id": tid, "type": t["type"], "from": [old["lon"], old["lat"]],
                       "text": f"{typ}: нових повідомлень немає з {_hm(t.get('last'))}. Позначку втрачено — це не відбій"})
            continue
        if old.get("next") != t.get("next") and t.get("next"):
            who = None
            if ev_of:
                items = (ev_of(tid) or {}).get("items") or []
                ch = [i for i in items if i.get("t", 0) > since and i.get("why") in ("змінило курс", "змінило позицію", "нова ціль", "підтвердження") and i.get("dest")]
                if ch:
                    who = ch[-1]
            ev.append({"k": "course", "t": (who or {}).get("t") or t.get("last") or now, "id": tid, "type": t["type"],
                       "from": [old["lon"], old["lat"]], "to": [t["lon"], t["lat"]],
                       "text": f"{typ}: курс уточнено" + (f" (було → {old['next']})" if old.get("next") else "") + f", тепер → {t['next']}"
                               + (f" — {who['src']} о {_hm(who['t'])}" if who else ""),
                       "src": (who or {}).get("src")})
            continue
        if st == "active" and abs(d - d_old) >= 15:
            ev.append({"k": "closer" if d < d_old else "away", "t": t.get("last") or now, "id": tid, "type": t["type"],
                       "from": [old["lon"], old["lat"]], "to": [t["lon"], t["lat"]],
                       "text": f"{typ}: {'наблизилась' if d < d_old else 'віддаляється'} — {round(d_old)} → {round(d)} км"})
    # цілі, що були поруч, а тепер їх немає зовсім у знімку (давно зникли)
    for tid, old in then_tr.items():
        if tid in now_tr:
            continue
        rel_old, d_old = _relevant(old, H, r_km)
        if rel_old:
            ev.append({"k": "lost", "t": then["t"], "id": tid, "type": old["type"], "from": [old["lon"], old["lat"]],
                       "text": f"{names.get(old['type'], old['type'])}: давно немає нових повідомлень. Позначку прибрано з мапи — це не відбій"})
    order = {"official": 0, "new": 1, "course": 2, "closer": 3, "closed": 4, "lost": 5, "away": 6}
    ev.sort(key=lambda e: (order.get(e["k"], 9), -e["t"]))
    cnt = {}
    for e in ev:
        cnt[e["k"]] = cnt.get(e["k"], 0) + 1
    return {"since": since, "now": now, "minutes": round((now - since) / 60) if now else None, "official_now": off_now,
            "events": ev[:12], "count": cnt, "total": len(ev), "had_frame": then is not None}


def _hm(t) -> str:
    if not t:
        return "?"
    import time as _t
    return _t.strftime("%H:%M", _t.localtime(t))
