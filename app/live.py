"""«SKY: Живий ефір» (03.11): мапа сама розповідає, що змінилося, і відповідає на питання діями на мапі.

Принцип: модель НЕ малює й не вигадує. Сервер рахує різницю «що було, коли ви дивились» → «що зараз» лише з перевірених
даних (кадри машини часу, докази цілей, повідомлення про балістику, офіційні тривоги). Модель обирає з дозволених дій
(say / focus / highlight / dim / breakdown / sources / only_new / replay / region), і кожна дія може посилатися лише на
ідентифікатори з цієї різниці. Без моделі працює детермінований сценарій. Відліку до удару немає ніколи."""
from __future__ import annotations

import json
import math
import time

ACTIONS = {"say", "focus", "highlight", "dim", "breakdown", "sources", "only_new", "replay", "region", "overview"}

LIVE_SYSTEM = """Ти режисер «Живого ефіру» SKY. Тобі дано різницю між тим, що людина бачила востаннє, і тим, що зараз, для її району.
Склади короткий сценарій для мапи українською: 2–6 кроків, кожен — одне коротке речення (say) і, за потреби, одна дія мапи.
Дозволені дії: focus(ids) — наблизити до цілей; highlight(ids) — підсвітити; dim(true/false) — приглушити все інше;
breakdown(id) — розкласти лічильник «було → стало» зі згадками; sources(id) — показати першоджерела; only_new(true) — лише нове;
replay(from) — програти відрізок від часу; region(bbox) — показати ділянку; overview — загальний вигляд.
Посилайся ЛИШЕ на id з даних. Не вигадуй цілей, місць, чисел, часу, координат, підтверджень чи відбоїв. Без відліку до удару.
Спершу найважливіше для людини: що ближче до її дому, балістика, нові цілі; далі — зміни; зниклі — коротко.
Якщо є питання людини — відповідай саме на нього і обери дію, яка найкраще показує відповідь
(«скільки/чому стало N» → breakdown; «що змінилося» → only_new + highlight; «звідки відомо» → sources; ділянка → region).
Пиши без довгих тире."""

LIVE_TOOL = {
    "name": "script",
    "description": "Сценарій живого ефіру: кроки з реплікою й дією мапи.",
    "input_schema": {"type": "object", "properties": {"steps": {"type": "array", "items": {"type": "object", "properties": {
        "say": {"type": "string"},
        "action": {"type": "string", "enum": sorted(ACTIONS)},
        "ids": {"type": "array", "items": {"type": "string"}},
        "value": {"type": ["string", "number", "boolean", "null"]},
        "bbox": {"type": "array", "items": {"type": "number"}}}, "required": ["say"]}}}, "required": ["steps"]},
}


def _km(a, b) -> float:
    return math.hypot((a[0] - b[0]) * 71.6, (a[1] - b[1]) * 111.2)


def diff(state: dict, hist: list[dict], tracker, since: float, home: tuple | None, obl: str | None, bbox: list | None = None) -> dict:
    """Що змінилося з моменту since для району людини (≤120 км від дому, або її область, або обведена ділянка)."""
    from .geo import oblasts
    O = oblasts()
    now = state.get("now") or time.time()
    frame = None
    for f in hist:
        if f["t"] <= since + 30:
            frame = f
        else:
            break
    old = {t["id"]: t for t in (frame or {}).get("tracks", [])}

    def mine(lon, lat) -> bool:
        if bbox and len(bbox) == 4:
            return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]
        if home and _km((lon, lat), home) <= 120:
            return True
        return bool(obl) and O.of(lon, lat) == obl

    items, seen_ids = [], set()
    byid = {x.id: x for x in getattr(tracker, "tracks", [])}
    names = {k: (v or {}).get("name", k) for k, v in (state.get("sources") or {}).items()}
    for t in state.get("tracks", []):
        if t.get("status") != "active" or not mine(t["lon"], t["lat"]):
            continue
        seen_ids.add(t["id"])
        o = old.get(t["id"])
        trk = byid.get(t["id"])
        ev = list(trk.evidence) if trk is not None else []
        new_ev = [{"t": int(e["t"]), "src": e["src"], "name": names.get(e["src"], e["src"]), "text": (e.get("text") or "")[:160], "link": e.get("link"),
                   "why": e.get("why"), "copy": bool(e.get("orig"))} for e in ev if e.get("t", 0) > since]
        st = "new" if (t.get("first") or now) > since and not o else "changed" if o and (
            (o.get("count") or 1) != (t.get("count") or 1) or o.get("next") != t.get("next") or _km((o["lon"], o["lat"]), (t["lon"], t["lat"])) > 5
        ) else ("mentioned" if new_ev else "same")
        d = round(_km((t["lon"], t["lat"]), home)) if home else None
        items.append({"id": t["id"], "type": t["type"], "name": t["name"], "status": st, "count": t.get("count") or 1,
                      "count_was": (o.get("count") or 1) if o else None, "next": t.get("next"), "next_was": o.get("next") if o else None,
                      "lon": t["lon"], "lat": t["lat"], "km": d, "ai": bool(t.get("ai")), "mentions": new_ev[-6:],
                      "srcs": (t.get("ev") or {}).get("prim", [])[:4]})
    gone = [{"id": i, "type": o["type"], "next": o.get("next")} for i, o in old.items()
            if i not in {t["id"] for t in state.get("tracks", []) if t.get("status") == "active"} and mine(o["lon"], o["lat"])]
    bal = [e for e in state.get("bal", []) if e["t"] > since and (not obl or obl in e.get("obl", []) or "*" in e.get("obl", []))]
    lv_now = (state.get("levels") or {}).get(obl) if obl else None
    lv_was = ((frame or {}).get("levels") or {}).get(obl) if obl else None
    rank = {"new": 0, "changed": 1, "mentioned": 2, "same": 3}
    items.sort(key=lambda x: (rank[x["status"]], x["km"] if x["km"] is not None else 999))
    return {"since": int(since), "now": int(now), "minutes": max(0, round((now - since) / 60)), "obl": obl,
            "alert": {"now": bool(lv_now), "was": bool(lv_was)} if obl else None,
            "items": items[:25], "gone": gone[:10], "bal": [{"t": e["t"], "src": e["src"], "obl": e.get("obl"), "close": e.get("close"),
                                                            "txt": e.get("txt", "")[:120], "k": e.get("k")} for e in bal][-6:],
            "counts": {"new": sum(i["status"] == "new" for i in items), "changed": sum(i["status"] == "changed" for i in items),
                       "gone": len(gone), "active": len(items)}}


def fallback_script(d: dict, question: str | None = None) -> list[dict]:
    """Без моделі: чесний детермінований сценарій з тих самих даних."""
    c = d["counts"]
    steps = []
    m = d["minutes"]
    head = f"За {m} хв: " if m else "Зараз: "
    parts = []
    if c["new"]:
        parts.append(f"нових цілей {c['new']}")
    if c["changed"]:
        parts.append(f"змінилося {c['changed']}")
    if c["gone"]:
        parts.append(f"зникло з мапи {c['gone']}")
    if d.get("alert") and d["alert"]["now"] != d["alert"]["was"]:
        parts.append("оголошено тривогу" if d["alert"]["now"] else "тривогу знято")
    steps.append({"say": head + (", ".join(parts) if parts else "суттєвих змін у вашому районі немає") + ".", "action": "overview"})
    if d["bal"]:
        b = d["bal"][-1]
        steps.append({"say": ("Відбій балістики" if b.get("close") else "Повідомлення про балістику") + f" о {time.strftime('%H:%M', time.localtime(b['t']))}, {b['src']}.",
                      "action": "dim", "value": True})
    for it in [i for i in d["items"] if i["status"] in ("new", "changed")][:5]:
        say = it["name"] + (f" ×{it['count']}" if it["count"] > 1 else "")
        if it["status"] == "new":
            say += ", нова ціль"
        elif it["count_was"] and it["count_was"] != it["count"]:
            say += f": було {it['count_was']}, стало {it['count']}"
        elif it["next"] != it["next_was"] and it["next"]:
            say += f": курс тепер на {it['next']}"
        if it["km"] is not None:
            say += f", {it['km']} км від вас"
        if it["mentions"]:
            e = it["mentions"][-1]
            say += f". Останнє: {time.strftime('%H:%M', time.localtime(e['t']))}, {e.get('name') or e['src']}"
        act = "breakdown" if it["count_was"] and it["count_was"] != it["count"] else "focus"
        steps.append({"say": say + ".", "action": act, "ids": [it["id"]]})
    return steps


def validate(steps: list, d: dict) -> list[dict]:
    ids = {i["id"] for i in d["items"]} | {g["id"] for g in d["gone"]}
    out = []
    for s in steps[:8] if isinstance(steps, list) else []:
        if not isinstance(s, dict) or not isinstance(s.get("say"), str):
            continue
        a = s.get("action") if s.get("action") in ACTIONS else None
        good = [i for i in (s.get("ids") or []) if i in ids]
        if a in ("focus", "highlight", "breakdown", "sources") and not good:
            a = None  # посилання на неіснуючу ціль — дію відкидаємо, лишаємо лише репліку
        st = {"say": s["say"][:240].replace("—", ","), "action": a, "ids": good[:6]}
        if a == "region" and isinstance(s.get("bbox"), list) and len(s["bbox"]) == 4:
            st["bbox"] = [float(x) for x in s["bbox"]]
        if a in ("dim", "only_new"):
            st["value"] = bool(s.get("value", True))
        if a == "replay":
            st["value"] = max(d["since"], min(d["now"], float(s.get("value") or d["since"])))
        out.append(st)
    return out


async def narrate(llm, d: dict, question: str | None = None) -> dict:
    if llm is None or not llm.on:
        return {"steps": fallback_script(d, question), "by": "rules"}
    lite = dict(d, items=[{k: v for k, v in i.items() if k not in ("lon", "lat")} for i in d["items"]])
    user = (f"Питання людини: {question}\n" if question else "Людина щойно повернулась у застосунок.\n") + \
        "Дані (JSON):\n" + json.dumps(lite, ensure_ascii=False)[:9000]
    res, by = await llm.call(LIVE_SYSTEM, user, LIVE_TOOL, max_tokens=900)
    steps = validate((res or {}).get("steps") or [], d) if res else []
    if not steps:
        return {"steps": fallback_script(d, question), "by": "rules"}
    return {"steps": steps, "by": by}


# ---------------- «Радіо SKY» (03.11): голосові зведення — свій регіон, періодично сусіди й уся Україна
RADIO_SYSTEM = """Ти ведучий «Радіо SKY»: коротко і спокійно озвучуєш повітряну обстановку для слухача в укритті чи в дорозі.
Лише з даних, які тобі дали; не вигадуй цілей, місць, чисел, часу; без відліку до удару; без довгих тире.
2–4 коротких речення, природна усна мова українською, числа словами не обов'язково. Якщо змін немає, так і скажи одним реченням.
Якщо в області слухача тривога або балістика — почни з цього і нагадай про укриття."""


def _neighbors(obl: str) -> list[str]:
    from .geo import oblasts
    O = oblasts()
    try:
        cs = O.centroids() if hasattr(O, "centroids") else None
    except Exception:  # noqa: BLE001
        cs = None
    NB = {"Харківська": ["Сумська", "Полтавська", "Дніпропетровська", "Донецька", "Луганська"],
          "Сумська": ["Чернігівська", "Полтавська", "Харківська"], "Полтавська": ["Сумська", "Харківська", "Дніпропетровська", "Кіровоградська", "Черкаська", "Київська", "Чернігівська"],
          "Дніпропетровська": ["Харківська", "Полтавська", "Кіровоградська", "Миколаївська", "Херсонська", "Запорізька", "Донецька"],
          "Донецька": ["Харківська", "Луганська", "Дніпропетровська", "Запорізька"], "Запорізька": ["Дніпропетровська", "Донецька", "Херсонська"],
          "Київська": ["Київ", "Чернігівська", "Полтавська", "Черкаська", "Вінницька", "Житомирська"], "Київ": ["Київська"],
          "Чернігівська": ["Київська", "Сумська", "Полтавська"], "Черкаська": ["Київська", "Полтавська", "Кіровоградська", "Вінницька"],
          "Кіровоградська": ["Черкаська", "Полтавська", "Дніпропетровська", "Миколаївська", "Одеська", "Вінницька"],
          "Миколаївська": ["Одеська", "Кіровоградська", "Дніпропетровська", "Херсонська"], "Херсонська": ["Миколаївська", "Дніпропетровська", "Запорізька"],
          "Одеська": ["Миколаївська", "Кіровоградська", "Вінницька"], "Вінницька": ["Житомирська", "Київська", "Черкаська", "Кіровоградська", "Одеська", "Хмельницька"],
          "Житомирська": ["Київська", "Вінницька", "Хмельницька", "Рівненська"], "Хмельницька": ["Житомирська", "Вінницька", "Тернопільська", "Рівненська", "Чернівецька"],
          "Рівненська": ["Волинська", "Житомирська", "Хмельницька", "Тернопільська", "Львівська"], "Волинська": ["Рівненська", "Львівська"],
          "Львівська": ["Волинська", "Рівненська", "Тернопільська", "Івано-Франківська", "Закарпатська"], "Тернопільська": ["Львівська", "Рівненська", "Хмельницька", "Івано-Франківська", "Чернівецька"],
          "Івано-Франківська": ["Львівська", "Тернопільська", "Чернівецька", "Закарпатська"], "Чернівецька": ["Івано-Франківська", "Тернопільська", "Хмельницька", "Вінницька"],
          "Закарпатська": ["Львівська", "Івано-Франківська"], "Луганська": ["Харківська", "Донецька"]}
    _ = cs
    return NB.get(obl, [])


def radio_context(state: dict, hist: list, tracker, since: float, home, obl: str, scope: str) -> tuple[str, str]:
    """(контекст для моделі, запасний текст без моделі) для одного випуску."""
    from collections import Counter
    from .geo import oblasts
    O = oblasts()
    act = [t for t in state.get("tracks", []) if t.get("status") == "active"]
    by_obl = Counter()
    for t in act:
        o = O.of(t["lon"], t["lat"])
        if o:
            by_obl[o] += t.get("count") or 1
    levels = state.get("levels") or {}
    off = state.get("official") or {}
    alerts = set(levels) | set(off.get("alert_obl") or [])
    now = time.time()
    bal = [e for e in state.get("bal", []) if now - e["t"] < 1800 and not e.get("close")]
    if scope == "region":
        d = diff(state, hist, tracker, since, home, obl)
        c = d["counts"]
        near = [i for i in d["items"] if i["status"] != "same"][:5]
        ctx = (f"ВИПУСК: ваш регіон ({obl}). Тривога в області: {'так' if obl in alerts else 'ні'}. "
               f"Балістика/МіГ для області за 30 хв: {sum(1 for e in bal if obl in e.get('obl', []) or '*' in e.get('obl', []))}.\n"
               f"За {d['minutes']} хв: нових {c['new']}, змінилось {c['changed']}, зникло {c['gone']}, зараз у районі {c['active']}.\n" +
               "\n".join(f"- {i['name']}{' ×' + str(i['count']) if i['count'] > 1 else ''}: {i['status']}, "
                         f"{('курс на ' + i['next']) if i['next'] else 'курс невідомий'}, {i['km']} км від дому" for i in near))
        fb = fallback_script(d)[0]["say"]
        if obl in alerts:
            fb = f"У вашій області тривога. {fb} Будьте в укритті."
        return ctx, fb
    if scope == "neighbors":
        nb = _neighbors(obl)
        rows = [f"- {o}: тривога {'так' if o in alerts else 'ні'}, цілей {by_obl.get(o, 0)}" for o in nb]
        ctx = f"ВИПУСК: сусідні області для {obl}.\n" + "\n".join(rows)
        busy = [o for o in nb if by_obl.get(o, 0)]
        fb = ("У сусідніх областях: " + ", ".join(f"{o} ({by_obl[o]})" for o in busy) + ".") if busy else "У сусідніх областях цілей не фіксують."
        return ctx, fb
    types = Counter()
    for t in act:
        types[t["name"]] += t.get("count") or 1
    ctx = (f"ВИПУСК: уся Україна. Областей з тривогою: {len(alerts)}. Цілей у повітрі за даними каналів: {sum(types.values())}.\n"
           + "\n".join(f"- {k}: {v}" for k, v in types.most_common(6)) +
           f"\nНайбільше цілей: " + ", ".join(f"{o} ({n})" for o, n in by_obl.most_common(4)) +
           (f"\nПовідомлень про балістику/МіГ-31К за 30 хв: {len(bal)}" if bal else ""))
    fb = (f"По Україні тривога в {len(alerts)} областях. " + (f"У повітрі приблизно {sum(types.values())} цілей, найбільше: " +
          ", ".join(o for o, _n in by_obl.most_common(3)) + "." if types else "Цілей у повітрі не фіксують."))
    return ctx, fb


async def radio(llm, state, hist, tracker, since, home, obl, scope) -> dict:
    ctx, fb = radio_context(state, hist, tracker, since, home, obl, scope)
    if llm is None or not llm.on:
        return {"text": fb, "by": "rules", "scope": scope}
    txt, by = await llm.call(RADIO_SYSTEM, ctx, None, max_tokens=260)
    txt = (txt or "").strip().replace("—", ",")
    return {"text": txt or fb, "by": by if txt else "rules", "scope": scope}
