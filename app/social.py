"""Автопости SKY у Threads (офіційний Threads API Meta).

Вмикається лише коли на сервері задано THREADS_TOKEN (і за бажанням THREADS_USER_ID); SOCIAL_AUTOPOST=0 вимикає все.
Що публікується:
  * раз на добу вранці (09:10–12:00) — підсумок доби до 09:00 з кількістю цілей за типами;
  * під час офіційної тривоги в SOCIAL_OBLAST (типово Харківська), коли над областю є активні цілі, — коротке зведення,
    не частіше SOCIAL_MIN_GAP хвилин (типово 45) і лише якщо картина змінилась.
Без позицій ППО, влучань і точних адрес; у кожному пості — нагадування, що офіційна тривога головна.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
import time
from pathlib import Path

import httpx

log = logging.getLogger("social")

API = "https://graph.threads.net/v1.0"
SITE = "sky.navryx.com.ua"
TAIL = "Офіційна тривога — головний сигнал."
LABELS = {  # множина для зведень; невідомі типи йдуть у «інші»
    "shahed": "шахеди", "uav": "БпЛА", "jet": "реактивні БпЛА", "molniya": "«Молнії»", "lancet": "«Ланцети»",
    "cruise": "крилаті ракети", "banderol": "«Бандеролі»", "ballistic": "балістика", "kab": "КАБи", "rszv": "РСЗВ",
    "fpv": "FPV", "recon": "розвідники",
}
OBL_LOC = {"Харківська": "Харківщина", "Київська": "Київщина", "Дніпропетровська": "Дніпропетровщина", "Сумська": "Сумщина",
           "Полтавська": "Полтавщина", "Запорізька": "Запоріжжя", "Одеська": "Одещина", "Чернігівська": "Чернігівщина"}


def _store() -> Path:
    d = Path(os.environ["PERSIST_DIR"]) if os.environ.get("PERSIST_DIR") else Path(__file__).resolve().parent.parent / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d / "social"


def counts_text(by_type: dict) -> str:
    """{'shahed': 7, 'jet': 3} → '7 шахедів…' у вигляді «шахеди 7 · реактивні БпЛА 3»; найчисельніші першими."""
    items = sorted(((n, t) for t, n in by_type.items() if n), reverse=True)
    parts, other = [], 0
    for n, t in items:
        if t in LABELS and len(parts) < 5:
            parts.append(f"{LABELS[t]} {n}")
        else:
            other += n
    if other:
        parts.append(f"інші {other}")
    return " · ".join(parts)


def morning_text(day: str, by_type: dict) -> str | None:
    n = sum(v for v in by_type.values() if v)
    if not n:
        return None
    d = dt.date.fromisoformat(day)
    return (f"Доба до 09:00 {d.strftime('%d.%m')}: {n} повітряних цілей над Україною.\n"
            f"{counts_text(by_type)}\n\n"
            f"Маршрути за добу на мапі: {SITE}\n{TAIL}")


def alert_text(obl: str, hhmm: str, by_type: dict) -> str | None:
    n = sum(v for v in by_type.values() if v)
    if not n:
        return None
    loc = OBL_LOC.get(obl, obl + " обл.")
    return (f"{loc}, {hhmm}: тривога. Над областю зараз {n} {'ціль' if n == 1 else 'цілі' if n < 5 else 'цілей'}: {counts_text(by_type)}.\n\n"
            f"Куди летять — на мапі наживо: {SITE}\n{TAIL}")


class Threads:
    def __init__(self, daily=None) -> None:
        self.daily = daily
        self.token = os.getenv("THREADS_TOKEN", "").strip()
        self.user = os.getenv("THREADS_USER_ID", "").strip() or "me"
        self.on = bool(self.token) and os.getenv("SOCIAL_AUTOPOST", "1") != "0"
        self.obl = os.getenv("SOCIAL_OBLAST", "Харківська")
        self.gap = float(os.getenv("SOCIAL_MIN_GAP", "45")) * 60
        self.last_alert_t = 0.0
        self.last_sig: tuple | None = None
        st = _store()
        st.mkdir(parents=True, exist_ok=True)
        tf = st / "threads_token.txt"  # оновлений довгостроковий токен переживає перезапуск
        if tf.exists() and tf.stat().st_mtime > float(os.getenv("THREADS_TOKEN_SET", "0") or 0):
            self.token = tf.read_text().strip() or self.token

    async def post(self, text: str) -> bool:
        if not self.on:
            return False
        try:
            async with httpx.AsyncClient(timeout=20) as cli:
                r = await cli.post(f"{API}/{self.user}/threads", data={"media_type": "TEXT", "text": text[:490], "access_token": self.token})
                cid = r.json().get("id")
                if not cid:
                    log.warning("threads: контейнер не створено: %s", r.text[:300])
                    return False
                await asyncio.sleep(3)
                r = await cli.post(f"{API}/{self.user}/threads_publish", data={"creation_id": cid, "access_token": self.token})
                ok = bool(r.json().get("id"))
                log.info("threads: %s", "опубліковано" if ok else r.text[:300])
                return ok
        except Exception:  # noqa: BLE001
            log.exception("threads post")
            return False

    async def refresh(self) -> None:
        """Довгостроковий токен Threads живе 60 днів; оновлюємо раз на тиждень."""
        try:
            async with httpx.AsyncClient(timeout=20) as cli:
                r = await cli.get("https://graph.threads.net/refresh_access_token",
                                  params={"grant_type": "th_refresh_token", "access_token": self.token})
                tok = r.json().get("access_token")
            if tok:
                self.token = tok
                (_store() / "threads_token.txt").write_text(tok)
                log.info("threads: токен оновлено")
        except Exception:  # noqa: BLE001
            log.exception("threads refresh")

    def _alert_counts(self, st: dict) -> dict:
        from .geo import oblasts
        O = oblasts()
        c: dict = {}
        for t in st.get("tracks") or []:
            if t.get("status") != "active" or t.get("lat") is None:
                continue
            if O.of(t["lon"], t["lat"]) == self.obl:
                c[t.get("type")] = c.get(t.get("type"), 0) + max(1, int(t.get("count") or 1))
        return c

    async def tick(self, st: dict, now: float | None = None) -> str | None:
        """Один крок: повертає текст опублікованого поста (для тестів і журналу) або None."""
        from .daily import kyiv_offset, last_finished, window
        now = now or time.time()
        hour = (now / 3600 + kyiv_offset(now)) % 24
        # ранковий підсумок доби
        if self.daily is not None and 9 + 10 / 60 <= hour < 12:
            day = last_finished(now)
            flag = _store() / f"morning-{day}"
            c = (getattr(self.daily, "cache", {}) or {}).get(day)
            if not flag.exists() and c and c.get("built", 0) >= window(day)[1]:
                txt = morning_text(day, c.get("by_type") or {})
                flag.write_text("1")
                if txt and await self.post(txt):
                    return txt
        # тривога в області з активними цілями
        off = st.get("official") or {}
        if self.obl in (off.get("alert_obl") or []):
            c = self._alert_counts(st)
            sig = tuple(sorted(c.items()))
            if c and sig != self.last_sig and now - self.last_alert_t >= self.gap:
                local = dt.datetime.fromtimestamp(now + kyiv_offset(now) * 3600, dt.timezone.utc)
                txt = alert_text(self.obl, local.strftime("%H:%M"), c)
                self.last_sig, self.last_alert_t = sig, now
                if txt and await self.post(txt):
                    return txt
        else:
            self.last_sig = None
        return None

    async def run(self, state) -> None:
        if not self.on:
            log.info("threads: автопости вимкнено (немає THREADS_TOKEN або SOCIAL_AUTOPOST=0)")
            return
        log.info("threads: автопости увімкнено, область %s, інтервал %d хв", self.obl, self.gap // 60)
        await asyncio.sleep(60)
        last_ref = 0.0
        while True:
            try:
                if time.time() - last_ref > 7 * 86400:
                    await self.refresh()
                    last_ref = time.time()
                await self.tick(state())
            except Exception:  # noqa: BLE001
                log.exception("threads tick")
            await asyncio.sleep(60)
