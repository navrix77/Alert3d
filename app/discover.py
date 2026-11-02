"""Автопошук нових джерел при кожному запуску сервера (і далі кожні 6 год) — лише з доказами.

1) Кандидати: канали, на які посилаються/з яких пересилають уже відомі монітори (≥2 різні канали-рекомендатори).
2) Перевірка: читаємо сторінку кандидата t.me/s/<name> і проганяємо дописи через наш парсер.
   Приймаємо, якщо свіжі (останній допис < 12 год), ≥5 дописів дають ціль з місцем і це ≥25% усіх дописів.
3) Прийняті канали одразу підключаються до моніторингу з низькою початковою довірою (0.45) —
   далі довіру вчить brain за підтвердженнями. Усе записується в sources_auto.json разом із доказами.
"""
from __future__ import annotations

import asyncio
import collections
import json
import logging
import os
import re
import time
from pathlib import Path

import httpx

from . import config
from .tg_web import UA, parse_page

log = logging.getLogger("discover")
FILE = Path(os.getenv("PERSIST_DIR") or Path(__file__).resolve().parent.parent / "data") / "sources_auto.json"
FWD = re.compile(r'tgme_widget_message_forwarded_from_name"[^>]*href="https://t\.me/([A-Za-z0-9_]{5,32})')
LINK = re.compile(r'href="https://t\.me/([A-Za-z0-9_]{5,32})(?:/\d+)?"')
MENTION = re.compile(r'(?<![\w@])@([A-Za-z][A-Za-z0-9_]{4,31})\b')
SKIP = {"share", "joinchat", "addstickers", "proxy", "iv", "s", "c", "boost", "contact", "addlist", "telegram", "durov", "botfather"}


def load() -> list[dict]:
    try:
        return json.loads(FILE.read_text(encoding="utf-8")).get("accepted", [])
    except Exception:
        return []


def apply(rows: list[dict]) -> int:
    """Підключає прийняті канали до config (без перезапуску)."""
    from .tracker import Source
    have = {u.lower() for _k, u, *_ in config.CHANNELS}
    n = 0
    for r in rows:
        u = r["user"]
        if u.lower() in have:
            continue
        have.add(u.lower())
        config.CHANNELS.append((u, u, "@" + u, 0.45, False))
        config.SOURCES[u] = Source(u, "@" + u, 0.45, False, f"https://t.me/{u}")
        config.BY_USERNAME[u.lower()] = u
        if r.get("region"):
            config.CHANNEL_REGION[u] = r["region"]
        n += 1
    return n


class Discover:
    def __init__(self, parser) -> None:
        self.parser = parser
        self.state = {"last": 0, "checked": [], "accepted": load(), "rejected": {}}
        self.state["rejected"] = self._load_rejected()

    def _load_rejected(self) -> dict:
        try:
            return json.loads(FILE.read_text(encoding="utf-8")).get("rejected", {})
        except Exception:
            return {}

    def _save(self):
        try:
            FILE.write_text(json.dumps({"accepted": self.state["accepted"], "rejected": self.state["rejected"],
                                        "last": self.state["last"]}, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            log.warning("discover save: %s", e)

    def evaluate(self, user: str, page: str) -> dict:
        msgs = parse_page(page)
        now = time.time()
        hits, obl, samples = 0, collections.Counter(), []
        from .geo import oblasts
        O = oblasts()
        for _mid, ts, text in msgs:
            for seg in self.parser.segments(text):
                o = self.parser.parse(seg, None)
                if o.kind in ("track", "zone") and o.places:
                    hits += 1
                    p = o.places[0].place
                    obl[O.of(p.lon, p.lat) or "?"] += 1
                    if len(samples) < 3:
                        samples.append(seg[:160])
                    break
        last = max((ts for _m, ts, _t in msgs), default=0)
        ratio = hits / max(1, len(msgs))
        ok = bool(msgs) and now - last < 12 * 3600 and hits >= 5 and ratio >= 0.25
        top = obl.most_common(1)
        region = top[0][0] if top and top[0][0] != "?" and top[0][1] >= 0.6 * hits else None
        return {"user": user, "ok": ok, "posts": len(msgs), "hits": hits, "ratio": round(ratio, 2),
                "fresh_h": round((now - last) / 3600, 1) if last else None, "region": region, "samples": samples}

    async def run_once(self) -> dict:
        have = {u.lower() for _k, u, *_ in config.CHANNELS}
        refs: dict[str, set] = collections.defaultdict(set)
        chans = [(k, u) for k, u, *_ in config.CHANNELS]
        async with httpx.AsyncClient(timeout=15, headers=UA, follow_redirects=True) as cli:
            for k, u in chans:
                try:
                    r = await cli.get(f"https://t.me/s/{u}")
                    for c in set(FWD.findall(r.text)) | set(LINK.findall(r.text)) | set(MENTION.findall(r.text)):
                        cl = c.lower()
                        if cl not in have and cl not in SKIP and not cl.endswith("bot"):
                            refs[c].add(k)
                except Exception:
                    pass
                await asyncio.sleep(0.4)
            cands = sorted([c for c, s in refs.items() if len(s) >= 2 and c.lower() not in {x.lower() for x in self.state["rejected"]}],
                           key=lambda c: -len(refs[c]))[:25]
            checked, newly = [], []
            for c in cands:
                try:
                    r = await cli.get(f"https://t.me/s/{c}")
                    ev = self.evaluate(c, r.text)
                except Exception as e:
                    ev = {"user": c, "ok": False, "error": str(e)[:80]}
                ev["refs"] = sorted(refs[c])[:8]
                ev["t"] = int(time.time())
                checked.append(ev)
                if ev["ok"]:
                    self.state["accepted"].append(ev)
                    newly.append(ev)
                else:
                    self.state["rejected"][c] = {"t": ev["t"], "hits": ev.get("hits"), "posts": ev.get("posts")}
                await asyncio.sleep(0.6)
        added = apply(newly)
        self.state["last"] = int(time.time())
        self.state["checked"] = checked
        self._save()
        log.info("автопошук джерел: кандидатів %d, додано %d", len(cands), added)
        return {"candidates": len(cands), "added": added}

    async def run(self):
        apply(self.state["accepted"])
        await asyncio.sleep(90)  # даємо моніторингу стартувати
        while True:
            try:
                await self.run_once()
            except Exception as e:
                log.warning("discover: %s", e)
            await asyncio.sleep(6 * 3600)
