"""Зведення для поширення (04.11): картка «область, час, джерела» з постійним посиланням /b/<id>.
Зберігає знімок на момент створення (а не живі дані), тож пізніше відкрита картка показує, що бачили ТОДІ, і великим
написом свій вік. Без дому користувача: лише область. Без ШІ: тільки дані SKY."""
from __future__ import annotations

import html
import json
import secrets
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "data" / "briefs.jsonl"
_MEM: dict[str, dict] = {}
_LOADED = False

TW = {"shahed": ("шахед", "шахеди"), "jet": ("реактивний БпЛА", "реактивні БпЛА"), "cruise": ("крилата ракета", "крилаті ракети"),
      "ballistic": ("балістика", "балістика"), "kab": ("КАБ", "КАБи"), "molniya": ("«Молнія»", "«Молнії»"), "lancet": ("«Ланцет»", "«Ланцети»"),
      "recon": ("розвідувальний дрон", "розвідувальні дрони"), "geran5": ("«Герань-5»", "«Герані-5»"), "banderol": ("крилата ракета «Бандероль»", "«Бандеролі»"),
      "fpv": ("FPV-дрон", "FPV-дрони"), "fpvf": ("FPV на оптоволокні", "FPV на оптоволокні"), "rszv": ("РСЗВ", "РСЗВ")}


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    try:
        for ln in FILE.read_text(encoding="utf-8").splitlines()[-5000:]:
            b = json.loads(ln)
            _MEM[b["id"]] = b
    except (OSError, ValueError):
        pass


def make(state: dict, obl: str) -> dict:
    from .geo import oblasts
    _load()
    O = oblasts()
    now = int(state.get("now") or time.time())
    levels = state.get("levels") or {}
    off = state.get("official") or {}
    alert = obl in levels or obl in (off.get("alert_obl") or [])
    tr = [t for t in state.get("tracks", []) if t.get("status") == "active" and O.of(t["lon"], t["lat"]) == obl]
    by = Counter()
    for t in tr:
        by[t["type"]] += t.get("count") or 1
    items = []
    for t in sorted(tr, key=lambda x: -(x.get("last") or 0))[:6]:
        n = t.get("count") or 1
        w = TW.get(t["type"], (t.get("name") or "ціль",) * 2)
        at = (t.get("at") or [None])[0]
        items.append(((f"{n} " + w[1]) if n > 1 else w[0]) + (f" біля {at}" if at else "") + (f", курс на {t['next']}" if t.get("next") else "") +
                     ("" if at else " (місце не назване)"))
    srcs = Counter()
    names = {k: (v or {}).get("name", k) for k, v in (state.get("sources") or {}).items()}
    for t in tr:
        for s in ((t.get("ev") or {}).get("prim") or [])[:3]:
            srcs[names.get(s, s)] += 1
    fresh = ((state.get("fresh") or {}).get("obl") or {}).get(obl)
    b = {"id": secrets.token_urlsafe(6), "t": now, "obl": obl, "alert": alert,
         "counts": [[(TW.get(k, (k, k))[1] if v > 1 else TW.get(k, (k, k))[0]), v] for k, v in by.most_common()],
         "items": items, "sources": [s for s, _n in srcs.most_common(6)], "last_msg": int(fresh) if fresh else None}
    _MEM[b["id"]] = b
    try:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        with FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(b, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return b


def get(bid: str) -> dict | None:
    _load()
    return _MEM.get(bid)


def _kv(t: float, fmt: str) -> str:
    import datetime as _dt
    from zoneinfo import ZoneInfo
    return _dt.datetime.fromtimestamp(t, ZoneInfo("Europe/Kyiv")).strftime(fmt)


def page(b: dict, base: str) -> str:
    e = html.escape
    tm = _kv(b["t"], "%d.%m.%Y %H:%M")
    tot = sum(v for _k, v in b["counts"])
    summary = (f"{b['obl']} область: " + ("тривога" if b["alert"] else "тривоги немає") +
               (f", цілей за даними SKY: {tot}" if tot else ", цілей за даними SKY немає") + f". Станом на {tm}.")
    rows = "".join(f"<li>{e(x)}</li>" for x in b["items"]) or "<li>Цілей в області за даними SKY не було.</li>"
    cnt = " · ".join(f"{e(k)}: {v}" for k, v in b["counts"])
    src = ", ".join(e(s) for s in b["sources"]) or "—"
    return f"""<!doctype html><html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(b['obl'])} · {tm} · NAVRYX SKY</title>
<meta property="og:title" content="{e(b['obl'])} область · {tm}"><meta property="og:description" content="{e(summary)}">
<meta property="og:site_name" content="NAVRYX SKY"><meta name="description" content="{e(summary)}"><meta name="robots" content="noindex">
<style>:root{{color-scheme:dark}}body{{margin:0;background:#07090E;color:#DDE3EE;font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
main{{max-width:560px;margin:0 auto;padding:22px 16px 48px}}.age{{border-radius:14px;padding:12px 14px;font-weight:800;font-size:18px;margin-bottom:14px}}
.age.ok{{background:rgba(53,208,127,.12);color:#35D07F}}.age.old{{background:rgba(255,176,32,.14);color:#FFB020}}.age.stale{{background:rgba(255,77,94,.15);color:#FF6B6B}}
.age small{{display:block;font-weight:500;font-size:13.5px;opacity:.85;margin-top:2px}}
h1{{font-size:24px;margin:0 0 4px}}.st{{font-weight:700;margin:8px 0}}.st.on{{color:#FF6B6B}}.st.off{{color:#35D07F}}
ul{{padding-left:20px}}li{{margin:4px 0;color:#C3CBD9}}.m{{color:#7C879B;font-size:13.5px}}a.go{{display:inline-block;margin-top:16px;background:#2f6bff;color:#fff;
text-decoration:none;border-radius:999px;padding:10px 18px;font-weight:700}}.w{{border:1px solid rgba(255,176,32,.4);border-radius:12px;padding:10px 12px;color:#FFD9A0;font-size:13.5px;margin-top:18px}}</style></head>
<body><main>
<div class="age ok" id="age">Зведення станом на {tm}</div>
<h1>{e(b['obl'])} область</h1>
<div class="st {'on' if b['alert'] else 'off'}">{'Офіційна тривога' if b['alert'] else 'Офіційної тривоги не було'}</div>
<p class="m">{('За даними SKY: ' + cnt) if cnt else 'Цілей в області за даними SKY не було.'}</p>
<ul>{rows}</ul>
<p class="m">Джерела: {src}{(' · останнє повідомлення по області о ' + _kv(b['last_msg'], '%H:%M')) if b.get('last_msg') else ''}</p>
<a class="go" href="{e(base)}/">Відкрити живу мапу</a>
<div class="w">Це знімок на момент створення, а не живі дані. NAVRYX SKY не є офіційною системою оповіщення: орієнтуйтеся на сирени й застосунок «Повітряна тривога».</div>
</main>
<script>(function(){{var t={b['t']},el=document.getElementById('age');function f(){{var m=Math.max(0,Math.round((Date.now()/1000-t)/60));
var a=m<1?'щойно':m<60?m+' хв тому':Math.floor(m/60)+' год '+(m%60)+' хв тому';
el.className='age '+(m<10?'ok':m<60?'old':'stale');
el.innerHTML='Зведенню '+a.replace(' тому','')+(m<1?'':'')+'<small>'+(m<10?'Свіже зведення.':m<60?'Обстановка вже могла змінитись. Відкрийте живу мапу.':'Застаріле зведення: це історія, а не поточна обстановка.')+' Станом на {tm}.</small>';
if(m<1)el.innerHTML='Зведення щойно створено<small>Станом на {tm}.</small>';}}f();setInterval(f,30000);}})();</script>
</body></html>"""
