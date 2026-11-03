"""Мовна модель як «другий парсер» для сумнівних повідомлень (03.11).

Правила (app/parser.py) лишаються основними: вони швидкі й перевірені на журналі. Модель отримує лише повідомлення,
де правила, ймовірно, помилились: тип не визначено, хоча є слова руху; є невідоме слово/скорочення після «на/над/курс»;
місце поза областю регіонального каналу; зведення «N … в області: A, B, C».

Режими (LLM_MODE у .env):
  off     — вимкнено (так само, якщо немає ANTHROPIC_API_KEY);
  shadow  — за замовчуванням: модель відповідає, відповідь лише пишеться в data/llm.jsonl поруч із розбором правил.
            Мапу не змінює. Так ми міряємо, чи модель справді краща, перш ніж їй довіряти.
Ключ додає власник у .env на сервері; код його ніде не логує й не віддає назовні.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path

import httpx

log = logging.getLogger("llm")
OUT = Path(__file__).resolve().parent.parent / "data" / "llm.jsonl"
API = "https://api.anthropic.com/v1/messages"

TYPES = ["shahed", "jet", "geran5", "molniya", "lancet", "recon", "fpv", "fpvf", "cruise", "banderol", "ballistic", "kab",
         "rszv", "mig31", "strategic_aviation", "unknown"]

SYSTEM = """Ти розбираєш повідомлення українських Telegram-каналів моніторингу повітряних загроз (українською або російською).
Поверни лише факти з тексту, нічого не вигадуй. Назви населених пунктів і районів подай українською в називному відмінку
(«на Балаклею» → «Балаклія», «Большую Даниловку» → «Велика Данилівка»). Розшифровуй місцеві скорочення лише якщо певен
(Харків: ХГ — Холодна Гора, ЛГ — Лиса Гора, ХТЗ, СС — Північна Салтівка, БД/ВД — Велика Данилівка, МД — Мала Данилівка);
інакше лиши як є і познач uncertain.
Розрізняй: ціль у русі; зведення «N у області: A, B, C» (це поточні місця, не маршрут); новину/наслідки удару; статус тривоги
(«🟡 Харків та передмістя»); відбій; зліт носія (МіГ-31К, Ту-95МС) — це не пуск ракети; рекламу/підпис каналу.
«Зала (угроза ланцет)» — розвідник ZALA з можливою загрозою Ланцета, а не Ланцет поруч.
«над Харковом на П'ятихатки» — ціль над містом, курс на район П'ятихатки (не точка в центрі)."""

TOOL = {
    "name": "report",
    "description": "Структурований розбір одного повідомлення моніторингового каналу.",
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["target", "summary", "news", "alert_status", "all_clear", "carrier", "launch", "other"]},
            "type": {"type": "string", "enum": TYPES},
            "count": {"type": ["integer", "null"]},
            "now": {"type": "array", "items": {"type": "string"}, "description": "де ціль(і) зараз, як названо"},
            "to": {"type": "array", "items": {"type": "string"}, "description": "куди летить (курс), по порядку"},
            "from": {"type": "array", "items": {"type": "string"}, "description": "звідки"},
            "oblasts": {"type": "array", "items": {"type": "string"}, "description": "області, якщо названо"},
            "uncertain": {"type": "array", "items": {"type": "string"}, "description": "слова, які не вдалося впевнено розшифрувати"},
            "note": {"type": "string", "description": "коротко, чому так (одне речення)"},
        },
        "required": ["kind", "type", "now", "to", "from"],
    },
}

MOVE = re.compile(r"(?i)курс|на\s|над\s|в\s+район|біля|около|повз|мимо|от\s|від\s|через|вектор|напрям|направлен")
WORD_AFTER = re.compile(r"(?:на|над|курс(?:ом)?(?:\s+на)?|в\s+район[еі]|біля|около|от|від|через|повз|мимо|/)\s*([А-ЯІЇЄҐ][\w'’\-]+)")


class LLM:
    def __init__(self) -> None:
        self.key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.mode = os.getenv("LLM_MODE", "shadow").strip().lower()
        self.model = os.getenv("LLM_MODEL", "claude-haiku-5-5").strip()
        self.daily_max = int(os.getenv("LLM_DAILY_MAX", "1500"))
        self.q: asyncio.Queue | None = None
        self.day, self.used, self.errors, self.seen = "", 0, 0, {}
        self.last_error = ""

    @property
    def on(self) -> bool:
        return bool(self.key) and self.mode != "off"

    def stats(self) -> dict:
        return {"enabled": self.on, "mode": self.mode if self.on else "off", "model": self.model, "today": self.used,
                "daily_max": self.daily_max, "errors": self.errors, "last_error": self.last_error[:160]}

    # ---------- чи варто питати модель
    @staticmethod
    def suspicious(parser, text: str, src: str) -> str | None:
        from .config import CHANNEL_REGION
        from .geo import oblasts, phon
        try:
            segs = parser.segments(text)
            obs = [parser.parse(s, src) for s in segs]
        except Exception as e:  # noqa: BLE001
            return f"crash:{type(e).__name__}"
        t = text or ""
        if len(t) < 6 or len(t) > 600:
            return None
        if any(o.no_target for o in obs) and not any(o.places for o in obs):
            return None
        places = [r for o in obs for r in o.places]
        if all(o.type is None for o in obs) and MOVE.search(t) and re.search(r"(?i)бпла|бпл|дрон|шахед|шаболд|ракет|ціл|цел|ударн|реактив|мопед", t):
            return "no_type"
        got = {phon(r.place.name)[:4] for r in places}
        for m in WORD_AFTER.finditer(t):
            w = m.group(1)
            if len(w) >= 2 and phon(w)[:4] not in got and not re.search(r"(?i)щин|ччин|област|бпла|шахед|^схі", w):
                return f"unknown:{w}"
        reg = CHANNEL_REGION.get(src)
        if reg and "щин" not in t.lower() and "област" not in t.lower():
            for r in places:
                ob = oblasts().of(r.place.lon, r.place.lat)
                if ob and ob != reg and not reg.startswith(ob[:5]):
                    return f"far:{r.place.name}"
        if re.search(r"\d+\s+\S+\s+\S*\s*(?:в|по)\s+област", t) and len(places) >= 3:
            return "summary"
        return None

    def consider(self, parser, text: str, src: str, ts: float, link: str | None) -> None:
        """Викликається для кожного свіжого повідомлення; сама вирішує, чи питати модель (без блокування)."""
        if not self.on or self.q is None or time.time() - ts > 900:
            return
        why = self.suspicious(parser, text, src)
        if not why:
            return
        k = (src, text.strip()[:200])
        if k in self.seen:
            return
        self.seen[k] = ts
        if len(self.seen) > 5000:
            self.seen = dict(list(self.seen.items())[-2000:])
        rules = []
        try:
            for s in parser.segments(text):
                o = parser.parse(s, src)
                rules.append({"type": o.type, "kind": o.kind, "count": o.count, "places": [[r.place.name, r.role] for r in o.places]})
        except Exception:  # noqa: BLE001
            pass
        try:
            self.q.put_nowait({"t": ts, "src": src, "link": link, "text": text[:600], "why": why, "rules": rules})
        except asyncio.QueueFull:
            pass

    async def ask(self, cli: httpx.AsyncClient, text: str, src: str) -> dict:
        from .config import CHANNEL_REGION
        reg = CHANNEL_REGION.get(src) or "загальнонаціональний"
        body = {"model": self.model, "max_tokens": 600, "system": SYSTEM, "tools": [TOOL],
                "tool_choice": {"type": "tool", "name": "report"},
                "messages": [{"role": "user", "content": f"Канал: {src} (регіон каналу: {reg}).\nПовідомлення:\n{text}"}]}
        r = await cli.post(API, json=body, headers={"x-api-key": self.key, "anthropic-version": "2023-06-01",
                                                   "content-type": "application/json"}, timeout=30)
        r.raise_for_status()
        for c in r.json().get("content", []):
            if c.get("type") == "tool_use":
                return c.get("input") or {}
        return {}

    async def run(self) -> None:
        if not self.on:
            log.info("LLM вимкнено (немає ANTHROPIC_API_KEY або LLM_MODE=off)")
            return
        self.q = asyncio.Queue(maxsize=200)
        log.info("LLM: режим %s, модель %s, ліміт %d/добу", self.mode, self.model, self.daily_max)
        async with httpx.AsyncClient() as cli:
            while True:
                item = await self.q.get()
                d = time.strftime("%Y-%m-%d")
                if d != self.day:
                    self.day, self.used = d, 0
                if self.used >= self.daily_max:
                    continue
                self.used += 1
                t0 = time.time()
                try:
                    item["llm"] = await self.ask(cli, item["text"], item["src"])
                except Exception as e:  # noqa: BLE001
                    self.errors += 1
                    self.last_error = f"{type(e).__name__}: {e}".replace(self.key, "***") if self.key else str(e)
                    await asyncio.sleep(5)
                    continue
                item["ms"] = int((time.time() - t0) * 1000)
                try:
                    OUT.parent.mkdir(parents=True, exist_ok=True)
                    with OUT.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(item, ensure_ascii=False) + "\n")
                except OSError:
                    pass
                await asyncio.sleep(0.3)
