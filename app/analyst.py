"""Аналітик NAVRYX: не лише «що де летить», а що це означає.

Кожен висновок — з числами й посиланнями на цілі/повідомлення, з яких він зроблений (філософія NAVRYX:
жодного твердження без доказів). Розділи:
- хвиля: скільки цілей зараз, наростає чи спадає (нові цілі за 30 хв проти попередніх 30 хв);
- напрямки: групи цілей одного типу з близьким курсом в одній області — «коридори» атаки;
- цілі: куди летять за словами каналів (з часом підльоту) і ймовірність для областей на годину (прогноз-віяло);
- порівняння з попередніми ночами на ту саму годину;
- джерела: хто повідомляє першим і з якою затримкою інші (за журналом доби), частка перепостів;
- самоперевірка: точність навченого прогнозу проти наївного.
"""
from __future__ import annotations

import collections
import json
import math
import re
import statistics
import time

from .geo import bearing, dist_km, oblasts, to_xy

TYPE_UA = {"shahed": ("шахед", "шахеди", "шахедів"), "jet": ("реактивний", "реактивні", "реактивних"),
           "molniya": ("«Молнія»", "«Молнії»", "«Молній»"), "cruise": ("крилата ракета", "крилаті ракети", "крилатих ракет"),
           "ballistic": ("балістична", "балістичні", "балістичних"), "geran5": ("«Герань-5»", "«Герані-5»", "«Гераней-5»"),
           "banderol": ("«Бандероль»", "«Бандеролі»", "«Бандеролей»"), "rszv": ("РСЗВ", "РСЗВ", "РСЗВ"),
           "fpv": ("FPV", "FPV", "FPV"), "fpvf": ("FPV", "FPV", "FPV")}
DIR8 = ["північ", "північний схід", "схід", "південний схід", "південь", "південний захід", "захід", "північний захід"]
OBL_LOC = {"Харківська": "Харківщині", "Сумська": "Сумщині", "Полтавська": "Полтавщині", "Дніпропетровська": "Дніпропетровщині",
           "Донецька": "Донеччині", "Запорізька": "Запоріжжі", "Чернігівська": "Чернігівщині", "Київська": "Київщині",
           "Черкаська": "Черкащині", "Кіровоградська": "Кіровоградщині", "Миколаївська": "Миколаївщині", "Одеська": "Одещині",
           "Херсонська": "Херсонщині", "Вінницька": "Вінниччині", "Житомирська": "Житомирщині", "Хмельницька": "Хмельниччині",
           "Рівненська": "Рівненщині", "Волинська": "Волині", "Львівська": "Львівщині", "Тернопільська": "Тернопільщині",
           "Івано-Франківська": "Прикарпатті", "Закарпатська": "Закарпатті", "Чернівецька": "Буковині", "Луганська": "Луганщині",
           "Київ": "Києві", "Крим": "Криму"}
NIGHT_START_H = 18  # «ніч» атаки: 18:00 → 09:00 за Києвом

_CACHE: dict[str, tuple[float, object]] = {}


def plural(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def _kyiv_offset(ts: float) -> float:
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return datetime.fromtimestamp(ts, ZoneInfo("Europe/Kyiv")).utcoffset().total_seconds()
    except Exception:  # noqa: BLE001  (на Windows без tzdata)
        return 7200.0


def period_start(ts: float) -> tuple[float, str, float]:
    """Період доби за Києвом, до якого належить ts: ніч 18:00→09:00 або день 09:00→18:00 → (початок, назва, тривалість)."""
    off = _kyiv_offset(ts)
    loc = ts + off
    day0 = loc - loc % 86400
    h = (loc - day0) / 3600
    if h < 9:
        return day0 - 6 * 3600 - off, "ніч", 15 * 3600.0
    if h >= NIGHT_START_H:
        return day0 + NIGHT_START_H * 3600 - off, "ніч", 15 * 3600.0
    return day0 + 9 * 3600 - off, "день", 9 * 3600.0


def _norm_text(s: str) -> str:
    return re.sub(r"[^\w]+", " ", (s or "").lower()).strip()[:160]


def journal_groups(rows: list[tuple]) -> list[dict]:
    """Рядки журналу (t, src, track, type, text) → епізоди цілей: той самий id трека з перервою ≤ 3 год.
    Ідентифікатори треків після перезапуску сервера повторюються, тому розриваємо за часом."""
    by: dict[str, list] = collections.defaultdict(list)
    for t, src, track, typ, text in rows:
        if track:
            by[track].append((t, src, typ, text))
    out = []
    for tid, items in by.items():
        items.sort()
        cur = [items[0]]
        for it in items[1:]:
            if it[0] - cur[-1][0] > 3 * 3600:
                out.append((tid, cur))
                cur = [it]
            else:
                cur.append(it)
        out.append((tid, cur))
    groups = []
    for tid, items in out:
        types = collections.Counter(x[2] for x in items if x[2])
        first_by_src: dict[str, float] = {}
        copies: dict[str, int] = collections.Counter()
        total: dict[str, int] = collections.Counter()
        seen: dict[str, tuple[float, str]] = {}
        for t, src, _typ, text in items:
            total[src] += 1
            k = _norm_text(text)
            if k and k in seen and seen[k][1] != src and t - seen[k][0] < 300:
                copies[src] += 1  # той самий текст іншого каналу за 5 хв — перепост, а не незалежне джерело
                continue
            seen.setdefault(k, (t, src))
            first_by_src.setdefault(src, t)
        groups.append({"id": tid, "t0": items[0][0], "t1": items[-1][0], "type": types.most_common(1)[0][0] if types else None,
                       "first": first_by_src, "copies": copies, "total": total})
    return groups


def source_stats(groups: list[dict], min_groups: int = 20) -> list[dict]:
    st: dict[str, dict] = collections.defaultdict(lambda: {"groups": 0, "multi": 0, "first": 0, "lags": [], "msgs": 0, "copies": 0})
    for g in groups:
        f = g["first"]
        for s, n in g["total"].items():
            st[s]["msgs"] += n
            st[s]["copies"] += g["copies"].get(s, 0)
        for s in f:
            st[s]["groups"] += 1
        if len(f) < 2:
            continue
        t_first = min(f.values())
        # «хто перший» — лише серед тих, хто написав протягом 15 хв від першого: пізніша згадка — вже інша фаза польоту
        for s, t in ((s, t) for s, t in f.items() if t - t_first <= 900):
            st[s]["multi"] += 1
            if t == t_first:
                st[s]["first"] += 1
            else:
                st[s]["lags"].append(t - t_first)
    out = []
    for s, v in st.items():
        if v["multi"] < min_groups and not (v["msgs"] >= min_groups and v["copies"] / v["msgs"] >= 0.5):
            continue  # мало спільних цілей; але суцільних ретрансляторів показуємо — їх і треба бачити
        out.append({"src": s, "targets": v["groups"], "shared": v["multi"], "first_share": round(v["first"] / v["multi"], 2) if v["multi"] else 0.0,
                    "lag_med_s": int(statistics.median(v["lags"])) if v["lags"] else 0,
                    "copy_share": round(v["copies"] / v["msgs"], 2) if v["msgs"] else 0.0})
    # рейтинг «хто перший» — лише за достатньої кількості спільних цілей; ретранслятори з малою вибіркою — в кінці
    out.sort(key=lambda x: (x["shared"] < min_groups, -x["first_share"], x["lag_med_s"]))
    return out


def night_compare(groups: list[dict], now: float, nights: int = 7) -> dict:
    """Скільки цілей з початку цієї ночі (дня) до цього моменту — і скільки було на ту саму годину в попередні."""
    st, label, length = period_start(now)
    off = now - st
    tonight = collections.Counter()
    past: list[collections.Counter] = [collections.Counter() for _ in range(nights)]
    full: list[collections.Counter] = [collections.Counter() for _ in range(nights)]
    for g in groups:
        if not g["type"]:
            continue
        if st <= g["t0"] <= now:
            tonight[g["type"]] += 1
            continue
        for k in range(1, nights + 1):
            s0 = st - k * 86400
            if s0 <= g["t0"] < s0 + length:
                full[k - 1][g["type"]] += 1
                if g["t0"] <= s0 + off:
                    past[k - 1][g["type"]] += 1
    # охоплення: скільки каналів писали в кожен період. Порівнювати чесно лише періоди зі схожим охопленням
    # (журнал ріс разом зі списком джерел — інакше «вдвічі більше цілей» означало б «вдвічі більше каналів»)
    srcs_now = set()
    srcs_past: list[set] = [set() for _ in range(nights)]
    for g in groups:
        if st <= g["t0"] <= now:
            srcs_now |= set(g["total"])
        for k in range(1, nights + 1):
            s0 = st - k * 86400
            if s0 <= g["t0"] < s0 + length:
                srcs_past[k - 1] |= set(g["total"])
    have = [i for i in range(nights) if sum(full[i].values())]
    comparable = [i for i in have if srcs_now and abs(len(srcs_past[i]) - len(srcs_now)) <= 0.25 * len(srcs_now)]
    avg = statistics.mean(sum(past[i].values()) for i in comparable) if comparable else None
    return {"since": int(st), "period": label, "tonight": dict(tonight), "tonight_n": sum(tonight.values()), "channels_now": len(srcs_now),
            "past_same_time": [sum(past[i].values()) for i in have], "past_full": [sum(full[i].values()) for i in have],
            "past_channels": [len(srcs_past[i]) for i in have], "comparable": len(comparable),
            "avg_same_time": round(avg, 1) if avg is not None else None}


def corridors(active: list[dict]) -> list[dict]:
    """Групи цілей одного типу в одній області з близьким курсом (±35°)."""
    obl = oblasts()
    groups: list[dict] = []
    for tr in active:
        o = obl.of(tr["lon"], tr["lat"]) or "поза Україною"
        hd = tr.get("hd")
        g = next((g for g in groups if g["type"] == tr["type"] and g["obl"] == o and
                  (hd is None and g["hd"] is None or hd is not None and g["hd"] is not None and abs((hd - g["hd"] + 540) % 360 - 180) <= 35)), None)
        if g is None:
            g = {"type": tr["type"], "obl": o, "hd": hd, "ids": [], "n": 0, "next": collections.Counter(), "hds": [], "src": collections.Counter()}
            groups.append(g)
        if hd is not None:
            g["src"][tr.get("hd_src") or "movement"] += 1
        g["ids"].append(tr["id"])
        g["n"] += tr.get("count") or 1
        if hd is not None:
            g["hds"].append(hd)
        if tr.get("next"):
            g["next"][tr["next"]] += 1
    out = []
    for g in groups:
        hd = None
        if g["hds"]:
            sx = sum(math.sin(math.radians(h)) for h in g["hds"])
            cx = sum(math.cos(math.radians(h)) for h in g["hds"])
            hd = (math.degrees(math.atan2(sx, cx)) + 360) % 360
        out.append({"type": g["type"], "obl": g["obl"], "n": g["n"], "hd": None if hd is None else round(hd),
                    "dir": None if hd is None else DIR8[int((hd + 22.5) // 45) % 8], "next": [n for n, _ in g["next"].most_common(3)],
                    "hd_src": dict(g["src"]), "spread": _spread(g["hds"]), "ids": g["ids"]})
    out.sort(key=lambda g: -g["n"])
    return out


def _spread(hds: list[float]) -> int | None:
    """Розкид курсів у групі (кругове відхилення, град.): мале — цілі справді йдуть одним коридором."""
    if len(hds) < 2:
        return None
    sx = sum(math.sin(math.radians(h)) for h in hds) / len(hds)
    cx = sum(math.cos(math.radians(h)) for h in hds) / len(hds)
    r = min(1.0, math.hypot(sx, cx))
    return round(math.degrees(math.sqrt(max(0.0, -2 * math.log(max(r, 1e-9))))))


HD_SRC_UA = {"channels": "названий каналами пункт", "course": "курс, названий каналом", "learned": "навчені маршрути",
             "movement": "рух між позиціями", "from": "звідки летить"}


def direction_quality(active: list[dict]) -> dict:
    """Звідки відомий напрямок кожної активної цілі — щоб довіряти напрямкам свідомо."""
    c = collections.Counter()
    for tr in active:
        c[(tr.get("hd_src") or "movement") if tr.get("hd") is not None else "none"] += tr.get("count") or 1
    return dict(c)


def likely_next(active: list[dict]) -> list[dict]:
    """Куди ймовірно далі за досвідом попередніх перельотів — для цілей, про пункт призначення яких канали мовчать."""
    tg: dict[str, dict] = {}
    for tr in active:
        if tr.get("next") or not tr.get("pred_next"):
            continue
        n = tr["pred_next"]
        x = tg.setdefault(n, {"name": n, "n": 0, "p": 0.0, "types": collections.Counter(), "ids": []})
        x["n"] += tr.get("count") or 1
        x["p"] = max(x["p"], tr.get("pred_p") or 0)
        x["types"][tr["type"]] += 1
        x["ids"].append(tr["id"])
    out = sorted(tg.values(), key=lambda x: (-x["n"], -x["p"]))
    for x in out:
        x["types"] = dict(x["types"])
    return out


def targets(active: list[dict]) -> list[dict]:
    """Куди летять за словами каналів: пункт → скільки цілей, які типи, найближчий підліт."""
    tg: dict[str, dict] = {}
    for tr in active:
        n = tr.get("next")
        if not n or not tr.get("route"):
            continue
        lo, la = tr["route"][0]
        d = dist_km(to_xy(tr["lat"], tr["lon"]), to_xy(la, lo))
        eta = d / max(30, tr.get("speed") or 170) * 60
        x = tg.setdefault(n, {"name": n, "n": 0, "types": collections.Counter(), "eta_min": None, "ids": []})
        x["n"] += tr.get("count") or 1
        x["types"][tr["type"]] += 1
        x["ids"].append(tr["id"])
        x["eta_min"] = round(eta) if x["eta_min"] is None else min(x["eta_min"], round(eta))
    out = sorted(tg.values(), key=lambda x: (-x["n"], x["eta_min"] or 999))
    for x in out:
        x["types"] = dict(x["types"])
    return out


def wave(hist: list[dict], now: float) -> dict:
    """Нові цілі за останні 30 хв проти попередніх 30 хв (за хвилинними кадрами «машини часу»)."""
    first: dict[str, float] = {}
    for fr in hist:
        for t in fr.get("tracks", []):
            first.setdefault(t["id"], fr["t"])
    new30 = sum(1 for t in first.values() if now - 1800 <= t <= now)
    prev30 = sum(1 for t in first.values() if now - 3600 <= t < now - 1800)
    peak = max((len(fr.get("tracks", [])) for fr in hist if now - fr["t"] < 12 * 3600), default=0)
    if new30 >= max(3, prev30 * 1.5):
        trend = "наростає"
    elif prev30 >= 3 and new30 <= prev30 * 0.5:
        trend = "спадає"
    else:
        trend = "стабільна"
    return {"new30": new30, "prev30": prev30, "trend": trend, "peak12h": peak}


def _types_phrase(c: dict) -> str:
    parts = [f"{n} {plural(n, TYPE_UA.get(t, (t, t, t)))}" for t, n in sorted(c.items(), key=lambda kv: -kv[1])]
    return ", ".join(parts)


def analyze(snap: dict, hist: list[dict], brain=None, now: float | None = None) -> dict:
    now = now or snap.get("now") or time.time()
    active = [t for t in snap.get("tracks", []) if t.get("status") == "active"]
    by_type = collections.Counter()
    for t in active:
        by_type[t["type"]] += t.get("count") or 1
    res: dict = {"t": int(now), "active": dict(by_type), "active_n": sum(by_type.values()),
                 "wave": wave(hist, now), "corridors": corridors(active), "targets": targets(active),
                 "likely_next": likely_next(active), "direction": direction_quality(active)}
    fc = (snap.get("forecast") or {}).get("oblasts") or {}
    res["oblast_p60"] = sorted(({"obl": o, "p60": v.get("p60"), "n60": v.get("n60")} for o, v in fc.items() if (v.get("p60") or 0) >= 0.2),
                               key=lambda x: (-round(x["p60"] or 0, 1), -(x["n60"] or 0)))[:6]
    res["launches"] = [{"site": L["site"], "type": L.get("type"), "count": L.get("count"), "t": L["t"], "srcs": L.get("srcs", [])}
                       for L in snap.get("launches", []) if now - L["t"] < 3 * 3600][:8]
    # журнал: джерела й порівняння ночей (дорогий запит — кеш 5 хв)
    jr = _CACHE.get("journal")
    if brain is not None and (not jr or now - jr[0] > 300):
        try:
            with brain.lock:
                rows = brain.db.execute("SELECT t, src, track, type, text FROM msg WHERE kind='track' AND t > ? ORDER BY t",
                                        (now - 8 * 86400,)).fetchall()
            g = journal_groups(rows)
            day = [x for x in g if x["t0"] > now - 86400]
            jr = (now, {"sources": source_stats(day), "nights": night_compare(g, now)})
            _CACHE["journal"] = jr
        except Exception:  # noqa: BLE001
            jr = jr or (now, {"sources": [], "nights": None})
    jd = jr[1] if jr else {"sources": [], "nights": None}
    res["sources"] = jd["sources"][:24]
    res["nights"] = jd["nights"]
    res["self"] = {"pred_acc": brain.pred_acc() if brain is not None and hasattr(brain, "pred_acc") else {},
                   "hd_acc": brain.hd_acc() if brain is not None and hasattr(brain, "hd_acc") else {}}
    res["summary"] = summary(res)
    return res


def summary(r: dict) -> list[str]:
    """Аналітична довідка людською мовою — кожен рядок спирається на числа з розділів вище."""
    out = []
    w = r["wave"]
    if r["active_n"]:
        out.append(f"Зараз у повітрі {r['active_n']} {plural(r['active_n'], ('ціль', 'цілі', 'цілей'))}: {_types_phrase(r['active'])}. "
                   f"Хвиля {w['trend']}: за 30 хв {w['new30']} нових (перед тим {w['prev30']}).")
    else:
        out.append("Зараз активних цілей немає." + (f" За останні 30 хв з'явилось {w['new30']}." if w["new30"] else ""))
    big = [c for c in r["corridors"] if c["n"] >= 2][:3]
    if big:
        parts = []
        for c in big:
            s = f"{c['n']} {plural(c['n'], TYPE_UA.get(c['type'], (c['type'],) * 3))} на {OBL_LOC.get(c['obl'], c['obl'])}"
            if c["dir"]:
                s += f", курс на {c['dir']}"
            if c["next"]:
                s += f" (→ {', '.join(c['next'][:2])})"
            parts.append(s)
        out.append("Головні напрямки: " + "; ".join(parts) + ".")
    dq = r.get("direction") or {}
    known = sum(v for k, v in dq.items() if k != "none")
    if r["active_n"] and dq:
        parts = [f"{HD_SRC_UA.get(k, k)} — {v}" for k, v in sorted(dq.items(), key=lambda kv: -kv[1]) if k != "none"]
        out.append(f"Напрямок відомий для {known} з {r['active_n']}" + (": " + ", ".join(parts) if parts else "") + "."
                   + (f" Без курсу: {dq['none']}." if dq.get("none") else ""))
    ln = r.get("likely_next") or []
    if ln:
        out.append("Канали не назвали куди, але за попередніми перельотами ймовірно далі: " + "; ".join(
            f"{x['name']} ({x['n']} {plural(x['n'], ('ціль', 'цілі', 'цілей'))}, {round(x['p'] * 100)}%)" for x in ln[:3]) + ".")
    tg = r["targets"][:3]
    if tg:
        out.append("Куди летять за словами каналів: " + "; ".join(
            f"{x['name']} — {x['n']} {plural(x['n'], ('ціль', 'цілі', 'цілей'))}" + (f", найближча ≈{x['eta_min']} хв" if x["eta_min"] is not None else "")
            for x in tg) + ".")
    if r["oblast_p60"]:
        def fo(o):
            if (o["p60"] or 0) >= 0.95 and o.get("n60"):  # 100% нічого не каже — кажемо, скільки цілей очікується
                return f"{o['obl']} ≈{o['n60']:g}"
            return f"{o['obl']} {round(o['p60'] * 100)}%"
        out.append("Прогноз на годину (ймовірність заходу або очікувана кількість цілей): " + ", ".join(fo(o) for o in r["oblast_p60"][:4]) + ".")
    if r["launches"]:
        L = r["launches"][0]
        out.append(f"Останній зафіксований пуск: {L['site']}" + (f", {L['count']} {plural(L['count'], ('ціль', 'цілі', 'цілей'))}" if L.get("count") else "") + ".")
    n = r.get("nights")
    if n and n.get("avg_same_time") and n["tonight_n"] is not None:
        a = n["avg_same_time"]
        k = n["tonight_n"] / a if a else None
        cmp_ = "більше" if k and k > 1.2 else ("менше" if k is not None and k < 0.8 else "приблизно стільки ж")
        since = "Від 18:00" if n.get("period") == "ніч" else "Від 09:00"
        prev = "у попередні ночі" if n.get("period") == "ніч" else "у попередні дні"
        out.append(f"{since} — {n['tonight_n']} {plural(n['tonight_n'], ('трек', 'треки', 'треків'))} цілей; {prev} зі схожим охопленням каналів "
                   f"({n['comparable']}) на цю годину в середньому {a} — {cmp_}" + (f" (×{k:.1f})" if k and cmp_ != "приблизно стільки ж" else "") + ".")
    fast = [x for x in r["sources"] if x["shared"] >= 20]
    if fast:
        s = fast[0]
        out.append(f"Найшвидше джерело за добу: {s['src']} — першим у {round(s['first_share'] * 100)}% із {s['shared']} спільних цілей"
                   + (f"; коли не перший — відстає в середньому на {round(s['lag_med_s'] / 60, 1)} хв" if s["lag_med_s"] else "") + ".")
    if r["sources"]:
        cp = [x for x in r["sources"] if x["copy_share"] >= 0.5]
        if cp:
            out.append("Переважно дублюють інших (не незалежні підтвердження): " + ", ".join(f"{x['src']} ({round(x['copy_share'] * 100)}% перепостів)" for x in cp[:4]) + ".")
    ha = r["self"].get("hd_acc") or {}
    if ha:
        out.append("Самоперевірка напрямку (курс на мапі збігся з наступною названою позицією в межах 45°): " + ", ".join(
            f"{TYPE_UA.get(t, (t,))[0]} {round(v['acc'] * 100)}% з {v['n']}" for t, v in ha.items()) + ".")
    pa = r["self"].get("pred_acc") or {}
    if pa:
        out.append("Самоперевірка прогнозу «ймовірно далі»: " + ", ".join(
            f"{TYPE_UA.get(t, (t,))[0]} {round(v['acc'] * 100)}% з {v['n']}" + (f" (наївний {round(v['naive'] * 100)}%)" if v.get("naive") is not None else "")
            for t, v in pa.items()) + ".")
    return out
