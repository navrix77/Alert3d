"""Мовна модель як «другий парсер» для сумнівних повідомлень (03.11).

Правила (app/parser.py) лишаються основними: вони швидкі й перевірені на журналі. Модель отримує лише повідомлення,
де правила, ймовірно, помилились: тип не визначено, хоча є слова руху; є невідоме слово/скорочення після «на/над/курс»;
місце поза областю регіонального каналу; зведення «N … в області: A, B, C».

Режими (LLM_MODE у .env): off / shadow / assist.
  assist  — те саме, що shadow, плюс: ціль, яку правила пропустили зовсім, а модель розпізнала і її місця пройшли
            перевірку газетиром і областю каналу, з'являється на мапі з позначкою «розпізнано ШІ»; підказки злиття
            «та сама ціль» з упевненістю ≥0.8 враховуються, лише якщо цілі поруч.
Режими детально:
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
    ("gemini", ("GEMINI_API_KEY",), "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
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
        self.ensemble = os.getenv("LLM_ENSEMBLE", "all").strip().lower() != "off"  # усі моделі голосують
        # допомога на мапі (власник 03.11: «по максимуму»): лише за згоди більшості моделей + перевірки правилами;
        # вимкнути без зміни коду: LLM_ASSIST=0 (тоді лише журнал)
        self.assist = self.mode != "off" and (self.mode == "assist" or os.getenv("LLM_ASSIST", "1").strip() != "0")
        self.used_p: dict[str, int] = {}
        self.err_by: dict[str, str] = {}   # остання помилка кожного провайдера (без ключів)
        self.ok_by: dict[str, int] = {}    # скільки вдалих відповідей сьогодні
        self.off: dict[str, float] = {}    # провайдер → до якого часу не питати (немає кредитів, неправильний ключ/модель, ліміт)
        self._secrets = [self.key] + [o[1] for o in self.others]
        self.cli = None
        self.on_ai = None      # assist: як додати ціль, розпізнану моделлю (задає main)
        self.on_merge = None   # assist: підказка злиття двох цілей (задає main)

    @property
    def on(self) -> bool:
        return bool(self.key or self.others) and self.mode != "off"

    def _clean(self, msg: str) -> str:
        for k in self._secrets:
            if k:
                msg = msg.replace(k, "***")
        return msg

    def stats(self) -> dict:
        return {"enabled": self.on, "mode": self.mode if self.on else "off", "assist": self.assist and self.on, "model": self.model if self.key else None,
                "ensemble": self.ensemble, "models": [o[0] + ":" + o[3] for o in self._chain()] if self.on else [],
                "today": self.used, "today_by": self.used_p,
                "daily_max": self.daily_max, "errors": self.errors, "last_error": self.last_error[:160],
                "providers": {o[0]: {"ok": self.ok_by.get(o[0], 0), "error": self.err_by.get(o[0], "")[:200],
                                     "paused_min": max(0, round((self.off.get(o[0], 0) - time.time()) / 60))} for o in self._chain()}}

    def _fail(self, prov: str, e: Exception) -> None:
        """Облік помилки й «запобіжник»: без кредитів / з неправильним ключем чи моделлю провайдер не смикаємо щоразу."""
        import httpx as _h
        self.errors += 1
        msg = f"{type(e).__name__}: {e}"
        if isinstance(e, _h.HTTPStatusError):
            st, body = e.response.status_code, (e.response.text or "")[:300]
            msg = f"HTTP {st}: {body}"
            low = body.lower()
            if st in (401, 402, 403) or (st == 429 and any(w in low for w in ("credit", "quota", "billing", "balance", "exceeded your"))):
                self.off[prov] = time.time() + 6 * 3600
            elif st in (400, 404) and "model" in low:
                self.off[prov] = time.time() + 6 * 3600
            elif st == 429:
                self.off[prov] = time.time() + 300
        self.err_by[prov] = self._clean(msg)
        self.last_error = self._clean(f"{prov}: {msg}")

    def _live(self, prov: str) -> bool:
        return self.off.get(prov, 0) <= time.time()

    def _ok(self, prov: str) -> None:
        self.ok_by[prov] = self.ok_by.get(prov, 0) + 1
        self.err_by.pop(prov, None)

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
        self.submit({"job": "parse", "t": ts, "src": src, "link": link, "text": text[:600], "why": why, "rules": rules})

    @staticmethod
    def _user(text: str, src: str) -> str:
        from .config import CHANNEL_REGION
        return f"Канал: {src} (регіон каналу: {CHANNEL_REGION.get(src) or 'загальнонаціональний'}).\nПовідомлення:\n{text}"

    # ---------- єдиний виклик моделі (будь-який провайдер з ланцюжка), з інструментом або текстом, з картинкою або без
    def _chain(self) -> list[tuple]:
        return ([("anthropic", self.key, "", self.model)] if self.key else []) + self.others

    def _budget(self) -> bool:
        d = time.strftime("%Y-%m-%d")
        if d != self.day:
            self.day, self.used = d, 0
        if self.used >= self.daily_max:
            return False
        self.used += 1
        return True

    async def _one(self, cli, prov, system: str, user: str, tool: dict | None, image: str | None, max_tokens: int):
        name, key, base, model = prov
        if name == "anthropic":
            content = ([{"type": "image", "source": {"type": "url", "url": image}}] if image else []) + [{"type": "text", "text": user}]
            body = {"model": model, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": content}]}
            if tool:
                body |= {"tools": [tool], "tool_choice": {"type": "tool", "name": tool["name"]}}
            r = await cli.post(API, json=body, headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}, timeout=40)
            r.raise_for_status()
            for c in r.json().get("content", []):
                if tool and c.get("type") == "tool_use":
                    return c.get("input") or {}
                if not tool and c.get("type") == "text":
                    return c.get("text", "")
            return {} if tool else ""
        content = [{"type": "text", "text": user}] + ([{"type": "image_url", "image_url": {"url": image}}] if image else [])
        body = {"model": model, "max_tokens": max_tokens, "temperature": 0,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": content if image else user}]}
        if tool:
            body |= {"tools": [{"type": "function", "function": {"name": tool["name"], "description": tool["description"], "parameters": tool["input_schema"]}}],
                     "tool_choice": {"type": "function", "function": {"name": tool["name"]}}}
        r = await cli.post(base + "/chat/completions", json=body, headers={"Authorization": f"Bearer {key}", "content-type": "application/json"}, timeout=40)
        r.raise_for_status()
        msg = (r.json().get("choices") or [{}])[0].get("message") or {}
        if not tool:
            return msg.get("content") or ""
        for tc in msg.get("tool_calls") or []:
            try:
                return json.loads(tc["function"]["arguments"])
            except (KeyError, ValueError):
                continue
        return {}

    async def call(self, system: str, user: str, tool: dict | None = None, image: str | None = None, max_tokens: int = 600,
                   skip: str | None = None, vision: bool = False):
        """Повертає (результат, хто відповів) або (None, None). Пробує провайдерів по черзі; для картинок — лише ті, що бачать зображення."""
        if self.cli is None or not self._budget():
            return None, None
        for prov in self._chain():
            tag = prov[0] + ":" + prov[3]
            if tag == skip or (vision and prov[0] not in VISION) or not self._live(prov[0]):
                continue
            try:
                res = await self._one(self.cli, prov, system, user, tool, image, max_tokens)
            except Exception as e:  # noqa: BLE001
                self._fail(prov[0], e)
                continue
            if res:
                self._ok(prov[0])
                return res, tag
        return None, None

    async def vote(self, system: str, user: str, tool: dict, image: str | None = None, max_tokens: int = 600) -> dict:
        """Ансамбль (власник 03.11: «усі моделі по максимуму, SKY унікальний»): той самий запит паралельно всім
        провайдерам з ключами (для картинок — тим, що бачать зображення). Повертає {хто: відповідь}."""
        if self.cli is None:
            return {}
        chain = [p_ for p_ in self._chain() if (not image or p_[0] in VISION) and self._live(p_[0])]
        if not self.ensemble:
            chain = chain[:1]
        async def one(prov):
            if not self._budget_p(prov[0]):
                return None
            try:
                out = prov[0] + ":" + prov[3], await self._one(self.cli, prov, system, user, tool, image, max_tokens)
                self._ok(prov[0])
                return out
            except Exception as e:  # noqa: BLE001
                self._fail(prov[0], e)
                return None
        res = await asyncio.gather(*(one(p_) for p_ in chain))
        return {k: v for k, v in (r for r in res if r) if v}

    def _budget_p(self, prov: str) -> bool:
        d = time.strftime("%Y-%m-%d")
        if d != self.day:
            self.day, self.used, self.used_p = d, 0, {}
        n = self.used_p.get(prov, 0)
        if n >= self.daily_max:
            return False
        self.used_p[prov] = n + 1
        self.used += 1
        return True

    async def transcribe(self, audio: bytes, ctype: str) -> tuple[str, str | None]:
        """Голос → текст (для iPhone, де браузер не розпізнає мову): Whisper через OpenAI або Groq, мова українська.
        Аудіо нікуди не зберігається."""
        ext = "mp4" if "mp4" in ctype or "aac" in ctype or "m4a" in ctype else "ogg" if "ogg" in ctype else "wav" if "wav" in ctype else "webm"
        cands = []
        for name, key, base, _m in self.others:
            if name == "openai":
                cands.append((name, key, base, os.getenv("LLM_STT_OPENAI", "whisper-1")))
            if name == "groq":
                cands.append((name, key, base, os.getenv("LLM_STT_GROQ", "whisper-large-v3")))
        async with httpx.AsyncClient() as cli:
            for name, key, base, model in cands:
                if not self._budget_p(name + "-stt"):
                    continue
                try:
                    r = await cli.post(base + "/audio/transcriptions", headers={"Authorization": f"Bearer {key}"},
                                       data={"model": model, "language": "uk", "prompt": "Шахед, реактивний, балістика, Харків, курсом на"},
                                       files={"file": (f"q.{ext}", audio, ctype or "application/octet-stream")}, timeout=40)
                    r.raise_for_status()
                    return (r.json().get("text") or "").strip(), name
                except Exception as e:  # noqa: BLE001
                    self.errors += 1
                    self.last_error = self._clean(f"{name} stt: {type(e).__name__}: {e}")
        return "", None

    def _log(self, item: dict) -> None:
        try:
            OUT.parent.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def submit(self, item: dict) -> None:
        if self.q is not None:
            try:
                self.q.put_nowait(item)
            except asyncio.QueueFull:
                pass

    # ---------- задачі
    async def _job_parse(self, item: dict) -> None:
        votes = await self.vote(SYSTEM, self._user(item["text"], item["src"]), TOOL)
        if not votes:
            return
        item["votes"] = votes
        item["llm"], item["agree"] = consensus(list(votes.values()))
        item["by"] = "+".join(sorted(votes))
        vs = list(votes.items())
        if len(vs) >= 2:  # сумісність зі звітом: перша й друга думки
            item["llm2"], item["by2"] = vs[1][1], vs[1][0]
        self._log(item)
        if self.assist and self.on_ai:
            try:
                item["applied"] = bool(self.on_ai(item))
            except Exception:  # noqa: BLE001
                log.exception("on_ai")

    async def _job_merge(self, item: dict) -> None:
        votes = await self.vote(MERGE_SYSTEM, item["prompt"], MERGE_TOOL, max_tokens=300)
        if not votes:
            return
        yes = [v for v in votes.values() if v.get("same") and float(v.get("confidence") or 0) >= 0.7]
        item["votes"], item["same_votes"], item["n_votes"] = votes, len(yes), len(votes)
        self._log({k: v for k, v in item.items() if k != "prompt"} | {"prompt": item["prompt"][:900]})
        # злиття лише за явної більшості моделей (одна модель — лише якщо вона одна підключена й упевнена ≥0.85)
        need = 2 if len(votes) >= 2 else 1
        strong = len(votes) >= 2 or (yes and float(yes[0].get("confidence") or 0) >= 0.85)
        if self.assist and self.on_merge and len(yes) >= need and len(yes) * 2 > len(votes) and strong:
            self.on_merge(item["a"], item["b"])

    async def _job_vision(self, item: dict) -> None:
        votes = await self.vote(VISION_SYSTEM, self._user(item.get("text") or "(лише зображення)", item["src"]), TOOL, image=item["image"])
        if not votes:
            return
        item["votes"] = votes
        item["llm"], item["agree"] = consensus(list(votes.values()))
        self._log(item)

    async def run(self) -> None:
        if not self.on:
            log.info("LLM вимкнено (немає ключів або LLM_MODE=off)")
            return
        self.q = asyncio.Queue(maxsize=300)
        log.info("LLM: режим %s, модель %s, ліміт %d/добу, резерв: %s", self.mode, self.model, self.daily_max,
                 ", ".join(o[0] for o in self.others) or "немає")
        async with httpx.AsyncClient() as cli:
            self.cli = cli
            while True:
                item = await self.q.get()
                t0 = time.time()
                try:
                    await {"parse": self._job_parse, "merge": self._job_merge, "vision": self._job_vision}[item.get("job", "parse")](item)
                except Exception:  # noqa: BLE001
                    log.exception("llm job")
                item["ms"] = int((time.time() - t0) * 1000)
                await asyncio.sleep(0.3)


def consensus(results: list[dict]) -> tuple[dict, float]:
    """Спільна відповідь ансамблю: тип і вид — більшістю; місця — ті, що назвала більшість моделей (за фонетичним ключем).
    Друге число — частка моделей, згодних з типом (1.0 = усі)."""
    from collections import Counter
    from .geo import phon
    rs = [r for r in results if isinstance(r, dict) and r]
    if not rs:
        return {}, 0.0
    if len(rs) == 1:
        return rs[0], 1.0
    typ, nt = Counter(r.get("type") for r in rs).most_common(1)[0]
    kind = Counter(r.get("kind") for r in rs).most_common(1)[0][0]
    out = {"kind": kind, "type": typ}
    for f in ("now", "to", "from", "oblasts"):
        cnt, first = Counter(), {}
        for r in rs:
            for n in {x for x in (r.get(f) or []) if isinstance(x, str)}:
                k = phon(n)[:6]
                cnt[k] += 1
                first.setdefault(k, n)
        out[f] = [first[k] for k, c in cnt.items() if c * 2 > len(rs)]
    cs = [r.get("count") for r in rs if isinstance(r.get("count"), int)]
    out["count"] = Counter(cs).most_common(1)[0][0] if cs and Counter(cs).most_common(1)[0][1] * 2 > len(rs) else None
    return out, round(nt / len(rs), 2)


# ---------- суддя «одна ціль чи дві»
MERGE_SYSTEM = """Ти аналітик моніторингу повітряних загроз. Дано дві цілі на мапі SKY і повідомлення каналів про кожну.
Скажи, чи це, найімовірніше, ТА САМА ціль (різні канали або різні назви місць) чи різні цілі.
Враховуй: «ще один», «новий», «другий», «група розділилась» означають різні цілі; той самий пункт призначення й близький час
від різних каналів, тип «невизначений» проти конкретного — часто та сама ціль; великі відстані за короткий час неможливі.
Не вигадуй фактів, яких немає в повідомленнях."""
MERGE_TOOL = {
    "name": "verdict",
    "description": "Чи це та сама ціль.",
    "input_schema": {"type": "object", "properties": {
        "same": {"type": "boolean"}, "confidence": {"type": "number", "description": "0..1"},
        "why": {"type": "string", "description": "одне речення"}}, "required": ["same", "confidence", "why"]},
}

# ---------- зображення з постів каналів (мапи зі стрілками, скріншоти)
VISION = {"anthropic", "openai", "gemini", "openrouter", "xai"}
VISION_SYSTEM = SYSTEM + """
Тобі дано ЗОБРАЖЕННЯ з поста (часто мапа зі стрілками й підписами) і підпис до нього. Витягни лише те, що на ньому
прямо видно: тип цілей, звідки й куди стрілки, підписані населені пункти. Якщо це не мапа загроз (реклама, фото наслідків,
мем) — kind=other. Не вгадуй назви, яких не видно."""

# ---------- «Що зараз відбувається?» для області
EXPLAIN_SYSTEM = """Ти пояснюєш мешканцю, що зараз відбувається в небі над його областю, лише за даними SKY, які тобі дали.
Пиши українською, коротко (3–6 речень), спокійно і по суті, без довгих тире. Не вигадуй цілей, місць, чисел і часу, яких немає в даних.
Якщо даних мало — так і скажи. Не давай прогнозу удару по конкретному місцю. Якщо є офіційна тривога в області дому —
нагадай про укриття. Наприкінці не додавай порад, крім укриття під час тривоги."""
