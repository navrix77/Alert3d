"""Мовна модель як «другий парсер» для сумнівних повідомлень (03.11).

Правила (app/parser.py) лишаються основними: вони швидкі й перевірені на журналі. Модель отримує лише повідомлення,
де правила, ймовірно, помилились: тип не визначено, хоча є слова руху; є невідоме слово/скорочення після «на/над/курс»;
місце поза областю регіонального каналу; зведення «N … в області: A, B, C».

Режими (LLM_MODE у .env):
  off     — вимкнено (так само, якщо немає ANTHROPIC_API_KEY);
  shadow  — за замовчуванням: модель відповідає, відповідь лише пишеться в data/llm.jsonl поруч із розбором правил.
            Мапу не змінює. Так ми міряємо, чи модель справді краща, перш ніж їй довіряти.
Ключ додає власник у .env на сервері; код його ніде не логує й не віддає назовні.

Резерв і друга думка: якщо Anthropic недоступний, запит іде наступному провайдеру з ключем у .env
(OpenRouter, Groq, OpenAI, Gemini, Mistral, SambaNova, Moonshot — усі через OpenAI-сумісний API).
LLM_SECOND_SHARE (0..1, за замовчуванням 0.2): частка повідомлень, які паралельно розбирає друга модель —
так нічний розбір бачить, де моделі згодні, а де ні (згода двох незалежних моделей = вища довіра).
Назви моделей можна змінити в .env (LLM_<ПРОВАЙДЕР>_MODEL), бо провайдери їх оновлюють.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
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

# OpenAI-сумісні провайдери: (назва, змінні з ключем, базова адреса, модель за замовчуванням)
PROVIDERS = [
    ("openrouter", ("OPENROUTER_API_KEY",), "https://openrouter.ai/api/v1", "openai/gpt-4o-mini"),
    ("groq", ("GROQ_API_KEY", "groq", "GROQ", "GROK", "grok"), "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    ("xai", ("XAI_API_KEY", "GROK", "grok", "GROQ", "groq"), "https://api.x.ai/v1", "grok-3-mini"),
    ("openai", ("OPENAI_API_KEY",), "https://api.openai.com/v1", "gpt-4o-mini"),
    ("gemini", ("GEMINI_API_KEY",), "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash"),
    ("mistral", ("MISTRAL_API_KEY",), "https://api.mistral.ai/v1", "mistral-small-latest"),
    ("sambanova", ("SAMBANOVA_API_KEY",), "https://api.sambanova.ai/v1", "Meta-Llama-3.3-70B-Instruct"),
    ("moonshot", ("MOONSHOT_API_KEY",), "https://api.moonshot.ai/v1", "moonshot-v1-8k"),
]


def _others() -> list[tuple[str, str, str, str]]:
    out = []
    for name, envs, base, model in PROVIDERS:
        # «GROK»/«groq» у файлі власника: Groq (ключ gsk_…) чи xAI Grok (ключ xai-…) — розрізняємо за префіксом
        keys = [os.getenv(e, "").strip() for e in envs if os.getenv(e, "").strip()]
        if name == "groq":
            keys = [k for k in keys if not k.startswith("xai-")]
        if name == "xai":
            keys = [k for k in keys if not k.startswith("gsk_")]
        key = keys[0] if keys else ""
        if key:
            out.append((name, key, base, os.getenv(f"LLM_{name.upper()}_MODEL", model).strip()))
    return out


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
        self.others = _others()
        self.second_share = float(os.getenv("LLM_SECOND_SHARE", "0.2"))
        self._secrets = [self.key] + [o[1] for o in self.others]

    @property
    def on(self) -> bool:
        return bool(self.key or self.others) and self.mode != "off"

    def _clean(self, msg: str) -> str:
        for k in self._secrets:
            if k:
                msg = msg.replace(k, "***")
        return msg

    def stats(self) -> dict:
        return {"enabled": self.on, "mode": self.mode if self.on else "off", "model": self.model if self.key else None,
                "fallback": [o[0] + ":" + o[3] for o in self.others], "second_share": self.second_share, "today": self.used,
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

    @staticmethod
    def _user(text: str, src: str) -> str:
        from .config import CHANNEL_REGION
        return f"Канал: {src} (регіон каналу: {CHANNEL_REGION.get(src) or 'загальнонаціональний'}).\nПовідомлення:\n{text}"

    async def ask_compat(self, cli: httpx.AsyncClient, prov: tuple, text: str, src: str) -> dict:
        """OpenAI-сумісний виклик з tool calling (та сама схема відповіді)."""
        name, key, base, model = prov
        body = {"model": model, "max_tokens": 600, "temperature": 0,
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": self._user(text, src)}],
                "tools": [{"type": "function", "function": {"name": TOOL["name"], "description": TOOL["description"], "parameters": TOOL["input_schema"]}}],
                "tool_choice": {"type": "function", "function": {"name": TOOL["name"]}}}
        r = await cli.post(base + "/chat/completions", json=body, headers={"Authorization": f"Bearer {key}", "content-type": "application/json"}, timeout=30)
        r.raise_for_status()
        msg = (r.json().get("choices") or [{}])[0].get("message") or {}
        for tc in msg.get("tool_calls") or []:
            try:
                return json.loads(tc["function"]["arguments"])
            except (KeyError, ValueError):
                continue
        return {}

    async def ask(self, cli: httpx.AsyncClient, text: str, src: str) -> dict:
        body = {"model": self.model, "max_tokens": 600, "system": SYSTEM, "tools": [TOOL],
                "tool_choice": {"type": "tool", "name": "report"},
                "messages": [{"role": "user", "content": self._user(text, src)}]}
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
                chain = ([("anthropic", self.key, "", self.model)] if self.key else []) + self.others
                for prov in chain:
                    try:
                        item["llm"] = await (self.ask(cli, item["text"], item["src"]) if prov[0] == "anthropic"
                                             else self.ask_compat(cli, prov, item["text"], item["src"]))
                        item["by"] = prov[0] + ":" + prov[3]
                        break
                    except Exception as e:  # noqa: BLE001
                        self.errors += 1
                        self.last_error = self._clean(f"{prov[0]}: {type(e).__name__}: {e}")
                if "llm" not in item:
                    await asyncio.sleep(5)
                    continue
                item["ms"] = int((time.time() - t0) * 1000)
                # друга думка іншої моделі для частини повідомлень: міра згоди для нічного розбору
                rest = [p_ for p_ in chain if p_[0] + ":" + p_[3] != item["by"]]
                if rest and random.random() < self.second_share:
                    p2 = rest[0]
                    try:
                        item["llm2"] = await (self.ask(cli, item["text"], item["src"]) if p2[0] == "anthropic"
                                              else self.ask_compat(cli, p2, item["text"], item["src"]))
                        item["by2"] = p2[0] + ":" + p2[3]
                    except Exception as e:  # noqa: BLE001
                        self.last_error = self._clean(f"{p2[0]}: {type(e).__name__}: {e}")
                try:
                    OUT.parent.mkdir(parents=True, exist_ok=True)
                    with OUT.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(item, ensure_ascii=False) + "\n")
                except OSError:
                    pass
                await asyncio.sleep(0.3)
