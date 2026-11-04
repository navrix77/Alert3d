"""Зв'язка мовної моделі з SKY (03.11): розпізнавання пропущеного правилами, суддя злиття цілей, картинки з постів,
«Що зараз відбувається?» і щодобове самонавчання. Усе працює лише з ключами в .env; без них — нічого не робить.
Модель ніколи не додає на мапу того, що не пройшло перевірки правилами: місця шукаємо в газетирі, область каналу,
тип — зі списку SKY. Усе, що вона дала, лишається в data/llm.jsonl для нічного розбору."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

log = logging.getLogger("ai")
ROOT = Path(__file__).resolve().parent.parent
DICT_FILE = ROOT / "data" / "llm_dict.json"
NIGHT_FILE = ROOT / "data" / "llm_night.json"

WORD = {"shahed": "Шахед", "jet": "Реактивний БпЛА", "geran5": "Герань-5", "molniya": "Молнія", "lancet": "Ланцет",
        "recon": "Розвідувальний БпЛА", "fpv": "FPV", "fpvf": "FPV на оптоволокні", "cruise": "Крилата ракета",
        "banderol": "Бандероль", "ballistic": "Балістика", "kab": "КАБ"}


EXOTIC = {"geran5": r"гер[ао]н\w*\W{0,3}5(?!\d)|гербер\w*\W{0,3}5(?!\d)", "banderol": r"бандерол", "lancet": r"ланцет|lancet",
          "molniya": r"молни|молні", "ballistic": r"баліст|баллист|іскандер|искандер|кинджал|кинжал|кн-23|kn-23",
          "cruise": r"ракет|крилат|крылат|калібр|калибр|х-\d", "kab": r"(^|\W)каб|бомб", "fpv": r"fpv|фпв", "fpvf": r"оптоволок",
          "recon": r"розвід|развед|орлан|zala|зала|суперкам|supercam|мерлін", "jet": r"реактив|турбо|р\.\s*шах|р\.\s*шабол"}


class AI:
    def __init__(self, llm, parser, tracker, state_fn) -> None:
        self.llm, self.p, self.trk, self.state = llm, parser, tracker, state_fn
        self.asked: dict = {}
        self.cache: dict = {}
        llm.on_ai = self.ai_ingest
        llm.on_merge = self.ai_merge

    # ---------- 1. ціль, яку правила пропустили
    def ai_ingest(self, item: dict) -> bool:
        """assist: правила не дали жодного місця або типу, модель дала ціль — перевіряємо правилами й додаємо з позначкою."""
        from .config import CHANNEL_REGION
        from .geo import oblasts
        m = item.get("llm") or {}
        rules = item.get("rules") or []
        if m.get("kind") != "target" or m.get("type") not in WORD:
            return False
        # 04.11: моделі назвали «Герань-2» Геранню-5, а значок ✈️ — «Бандероллю». Рідкісний тип приймаємо лише тоді,
        # коли його прямо названо в тексті; інакше звичайний ударний БпЛА (якщо текст про БпЛА) або нічого
        import re as _re
        low = (item.get("text") or "").lower()
        need = EXOTIC.get(m["type"])
        if need and not _re.search(need, low):
            if _re.search(r"бпла|безпілот|беспилот|шахед|герань|гербер|мопед|дрон", low):
                m = dict(m, type="shahed")
            else:
                return False
        votes = item.get("votes") or {}
        if len(votes) >= 2 and (item.get("agree", 0) < 0.6 or sum(1 for v in votes.values() if v.get("type") == m["type"]) < 2):
            return False  # кілька моделей і немає згоди хоча б двох — лише в журнал
        if any(r.get("places") and r.get("type") for r in rules):
            return False  # правила вже щось дали — не підміняємо, лише порівнюємо в журналі
        now, to, frm = (m.get("now") or [])[:1], (m.get("to") or [])[:3], (m.get("from") or [])[:1]
        if not (now or to):
            return False
        txt = WORD[m["type"]] + (f" над {now[0]}" if now else "") + (f" від {frm[0]}" if frm and not now else "") + \
            (" курсом на " + ", ".join(to) if to else "")
        obs = self.p.parse(txt, item["src"])
        if obs.type != m["type"] or not obs.places:
            return False
        reg = CHANNEL_REGION.get(item["src"])
        if reg:  # регіональний канал: усі місця в його області або сусідній (≤ 80 км від межі — грубо: та сама або сусідня область)
            obl = oblasts()
            for r in obs.places:
                o = obl.of(r.place.lon, r.place.lat)
                if o and o != reg and not reg.startswith(o[:5]) and o not in (m.get("oblasts") or []):
                    return False
        obs.raw = item["text"]
        obs.ai = True
        if m.get("count") and isinstance(m["count"], int) and 0 < m["count"] <= 15:
            obs.count = m["count"]
        self.trk.ingest(obs, item["src"], item["t"], item.get("link"))
        log.info("ШІ додав ціль: %s (%s)", txt, item["src"])
        return True

    # ---------- 2. суддя «одна ціль чи дві»
    def ai_merge(self, a: str, b: str) -> None:
        self.trk.ai_merge.add(frozenset((a, b)))

    async def merge_watch(self) -> None:
        while True:
            await asyncio.sleep(60)
            if not self.llm.on:
                continue
            now = time.time()
            cands = sorted(self.trk.merge_cands.items(), key=lambda x: -x[1])
            self.trk.merge_cands.clear()
            byid = {t.id: t for t in self.trk.tracks}
            n = 0
            for pair, _t in cands:
                if pair in self.asked or n >= 4:
                    continue
                a, b = sorted(pair)
                ta, tb = byid.get(a), byid.get(b)
                if not ta or not tb or ta.closed or tb.closed or ta.merged or tb.merged:
                    continue
                self.asked[pair] = now
                n += 1
                self.llm.submit({"job": "merge", "t": now, "a": a, "b": b, "prompt": self._pair(ta, tb, now)})
            if len(self.asked) > 3000:
                self.asked = dict(list(self.asked.items())[-1000:])

    @staticmethod
    def _desc(tr, now: float) -> str:
        from .geo import dist_km
        ev = [f"  {time.strftime('%H:%M', time.localtime(e['t']))} {e['src']}: {e.get('text', '')[:160]}" for e in tr.evidence[-5:]]
        return (f"{tr.id}: тип {tr.type}, к-сть {tr.count or 1}, останнє місце {getattr(tr.last, 'label', '?')} "
                f"({int((now - tr.last.t) / 60)} хв тому), курс {('на ' + tr.course_to) if tr.course_to else 'невідомий'}\n" + "\n".join(ev))

    def _pair(self, ta, tb, now: float) -> str:
        from .geo import dist_km
        d = dist_km(ta.est(now), tb.est(now))
        return f"Відстань між оцінками положень: {d:.0f} км.\nЦІЛЬ A\n{self._desc(ta, now)}\n\nЦІЛЬ B\n{self._desc(tb, now)}"

    # ---------- 3. картинки з постів
    def vision(self, text: str, src: str, ts: float, link: str | None, image: str) -> None:
        if self.llm.on and time.time() - ts < 900:
            self.llm.submit({"job": "vision", "t": ts, "src": src, "link": link, "text": (text or "")[:400], "image": image})

    # ---------- 4. «Що зараз відбувається?»
    async def explain(self, obl: str) -> dict:
        from .llm import EXPLAIN_SYSTEM
        if not self.llm.on:
            return {"ok": False, "text": "ШІ ще не підключено."}
        c = self.cache.get(obl)
        if c and time.time() - c[0] < 90:
            return c[1]
        s = self.state()
        from .geo import oblasts
        O = oblasts()
        tr = [t for t in s.get("tracks", []) if t.get("status") == "active" and O.of(t["lon"], t["lat"]) == obl]
        lines = [f"{t['name']}{' ×' + str(t['count']) if (t.get('count') or 1) > 1 else ''}: "
                 f"{'місце оцінене' if t.get('pos_est') else 'біля ' + (t.get('at') or [''])[0] if t.get('at') else 'біля названого пункту'}"
                 f"{', курс на ' + t['next'] if t.get('next') else ''}" for t in tr[:20]]
        off = (s.get("official") or {})
        alert = obl in (s.get("levels") or {}) or obl in (off.get("alert_obl") or [])
        bal = [e for e in s.get("bal", []) if (obl in e.get("obl", []) or "*" in e.get("obl", [])) and not e.get("close") and time.time() - e["t"] < 1800]
        kab = [z for z in s.get("zones", []) if z.get("obl") == obl]
        ctx = (f"Область: {obl}. Зараз {time.strftime('%H:%M')}.\nОфіційна тривога в області: {'так' if alert else 'ні'}.\n"
               f"Цілей в області (за повідомленнями каналів): {len(tr)}\n" + "\n".join(lines) +
               (f"\nПовідомлень про балістику/МіГ-31К/«Бандероль» за 30 хв: {len(bal)}" if bal else "") +
               (f"\nЗон загрози КАБ: {len(kab)}" if kab else ""))
        txt, by = await self.llm.call(EXPLAIN_SYSTEM, ctx, None, max_tokens=350)
        if not txt:  # усі моделі недоступні — чесне зведення з даних SKY, без вигадок
            txt = (f"Офіційна тривога в області: {'є' if alert else 'немає'}. "
                   + (f"За повідомленнями каналів цілей в області: {len(tr)}. " + "; ".join(lines[:5]) + "." if tr else "Цілей в області за повідомленнями каналів зараз немає.")
                   + (f" Повідомлень про балістику за 30 хв: {len(bal)}." if bal else "") + (f" Зон загрози КАБ: {len(kab)}." if kab else ""))
            by = "rules"
        out = {"ok": True, "text": txt.strip(), "by": by, "t": int(time.time()), "n": len(tr),
               "note": ("Оцінка ШІ за даними SKY" if by != "rules" else "Зведення з даних SKY (ШІ зараз недоступний)") + "; не замінює офіційних повідомлень"}
        self.cache[obl] = (time.time(), out)
        return out

    # ---------- 5. щодобове самонавчання: словник з невідомих слів + підсумок ночі
    async def daily(self, selfcheck_file: Path) -> None:
        while True:
            lt = time.localtime()
            await asyncio.sleep(((6 - lt.tm_hour) * 3600 + (10 - lt.tm_min) * 60 - lt.tm_sec) % 86400 or 86400)
            if not self.llm.on:
                continue
            try:
                await self._dict(selfcheck_file)
                await self._night()
            except Exception:  # noqa: BLE001
                log.exception("ai daily")

    async def _dict(self, selfcheck_file: Path) -> None:
        if not selfcheck_file.exists():
            return
        sc = json.loads(selfcheck_file.read_text(encoding="utf-8"))
        unk = sc.get("unknown_local_names") or []
        if not unk:
            return
        items = "\n".join(f"- [{u['reg']}] «{u['word']}» ×{u['n']}: {u['example'][2] if u.get('example') else ''}" for u in unk[:40])
        sys_ = ("Ти допомагаєш словнику місцевих назв для моніторингу повітряних загроз в Україні. Для кожного слова скажи, що це: "
                "населений пункт/район міста (назва українською в називному відмінку), скорочення (розшифровка), слово мови, "
                "назва каналу чи інше. Не вгадуй: якщо не знаєш — unknown. Відповідай лише JSON-масивом об'єктів "
                "{word, region, kind: place|abbr|word|channel|unknown, ukr_name, confidence 0..1, note}.")
        txt, by = await self.llm.call(sys_, items, None, max_tokens=1800)
        try:
            arr = json.loads(txt[txt.index("["): txt.rindex("]") + 1]) if txt else []
        except ValueError:
            arr = []
        DICT_FILE.write_text(json.dumps({"t": int(time.time()), "by": by, "proposals": arr}, ensure_ascii=False, indent=1), encoding="utf-8")

    async def _night(self) -> None:
        s = self.state()
        log_ = s.get("log", [])[-60:]
        if not log_:
            return
        lines = "\n".join(f"{time.strftime('%H:%M', time.localtime(x['t']))} {x['src']} {x.get('type') or ''} "
                          f"{', '.join(p['n'] for p in x.get('places', []))}" for x in log_)
        sys_ = ("Ти аналітик. За журналом повідомлень SKY напиши короткий підсумок ночі українською (5–8 речень): хвилі, типи, "
                "напрямки, найбільш уражені області. Лише з даних журналу, без вигадок, без довгих тире.")
        txt, by = await self.llm.call(sys_, lines, None, max_tokens=500)
        if txt:
            NIGHT_FILE.write_text(json.dumps({"t": int(time.time()), "by": by, "text": txt.strip()}, ensure_ascii=False), encoding="utf-8")
