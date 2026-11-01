"""Автономний моніторинг публічних Telegram-каналів через веб-версію t.me/s/<канал>.
Не потребує акаунта, api_id чи сесії. Опитує канали по колу, бере лише нові пости."""
from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from datetime import datetime

import httpx

from . import config

log = logging.getLogger("tg_web")
MSG = re.compile(r'<div class="tgme_widget_message[^"]*"[^>]*data-post="([^"/]+)/(\d+)"(.*?)(?=<div class="tgme_widget_message_wrap|\Z)', re.S)
TEXT = re.compile(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)
TIME = re.compile(r'<time[^>]*datetime="([^"]+)"')
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}


def _clean(fragment: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", fragment)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def parse_page(page: str) -> list[tuple[int, float, str]]:
    out = []
    for _ch, mid, body in MSG.findall(page):
        t = TIME.search(body)
        x = TEXT.search(body)
        if not t or not x:
            continue
        ts = datetime.fromisoformat(t.group(1)).timestamp()
        out.append((int(mid), ts, _clean(x.group(1))))
    return out


class WebMonitor:
    def __init__(self) -> None:
        self.last_id: dict[str, int] = {}
        self.last_ok: dict[str, float] = {}
        self.errors: dict[str, str] = {}

    def state(self) -> dict:
        now = time.time()
        live = [u for u, t in self.last_ok.items() if now - t < 420]
        return {"channels": len(config.CHANNELS), "live": len(live), "errors": dict(list(self.errors.items())[:5])}

    async def poll(self, cli: httpx.AsyncClient, key: str, user: str, on_message, backfill_sec: float) -> None:
        r = await cli.get(f"https://t.me/s/{user}")
        r.raise_for_status()
        msgs = parse_page(r.text)
        self.last_ok[user] = time.time()
        self.errors.pop(user, None)
        if not msgs:
            return
        first = user not in self.last_id
        lid = self.last_id.get(user, 0)
        cutoff = time.time() - backfill_sec
        for mid, ts, text in sorted(msgs):
            if mid <= lid or (first and ts < max(cutoff, time.time() - 1800)):
                continue
            on_message(text, key, ts, f"https://t.me/{user}/{mid}")
        self.last_id[user] = max(m[0] for m in msgs)

    async def crawl_history(self, days: int = 7, max_pages: int = 60) -> list[tuple[float, str, str, str]]:
        """Історія головних каналів за N днів (сторінками ?before=). Повільно й чемно, у фоні."""
        out = []
        since = time.time() - days * 86400
        async with httpx.AsyncClient(timeout=20, headers=UA, follow_redirects=True) as cli:
            for key, user, *_ in config.CHANNELS:
                if key not in config.FAST:
                    continue
                before = None
                for _ in range(max_pages):
                    try:
                        r = await cli.get(f"https://t.me/s/{user}" + (f"?before={before}" if before else ""))
                        msgs = parse_page(r.text)
                    except Exception:  # noqa: BLE001
                        break
                    if not msgs:
                        break
                    out += [(ts, text, key, f"https://t.me/{user}/{mid}") for mid, ts, text in msgs if ts >= since]
                    before = min(m[0] for m in msgs)
                    if min(m[1] for m in msgs) < since:
                        break
                    await asyncio.sleep(1.2)
        return out

    async def run(self, on_message) -> None:
        chans = [(k, u) for k, u, *_ in config.CHANNELS]
        # Перший прохід — дочитати останні 30 хв у хронологічному порядку по всіх каналах
        async with httpx.AsyncClient(timeout=15, headers=UA, follow_redirects=True) as cli:
            buf = []
            for key, user in [(k, u) for k, u in chans if k in config.FAST]:
                try:
                    r = await cli.get(f"https://t.me/s/{user}")
                    msgs = parse_page(r.text)
                    self.last_ok[user] = time.time()
                    self.last_id[user] = max((m[0] for m in msgs), default=0)
                    buf += [(ts, text, key, f"https://t.me/{user}/{mid}") for mid, ts, text in msgs if ts > time.time() - 1800]
                except Exception as e:  # noqa: BLE001
                    self.errors[user] = str(e)[:120]
                await asyncio.sleep(0.25)
            for ts, text, key, link in sorted(buf):
                on_message(text, key, ts, link)
            log.info("t.me/s: стартово прочитано %d постів; усього каналів у моніторингу: %d", len(buf), len(chans))
            # Далі — по колу; цикл ~ len(chans) * gap секунд
            fast = [(k, u) for k, u in chans if k in config.FAST]
            slow = [(k, u) for k, u in chans if k not in config.FAST]
            per_cycle_slow = 6
            gap = max(0.35, config.TG_WEB_CYCLE_SEC / max(1, len(fast) + per_cycle_slow))
            si = 0
            while True:
                batch = fast + [slow[(si + n) % len(slow)] for n in range(min(per_cycle_slow, len(slow)))]
                si = (si + per_cycle_slow) % max(1, len(slow))
                for key, user in batch:
                    try:
                        await self.poll(cli, key, user, on_message, 1800)
                    except httpx.HTTPStatusError as e:
                        self.errors[user] = f"HTTP {e.response.status_code}"
                        if e.response.status_code == 429:
                            await asyncio.sleep(20)
                    except Exception as e:  # noqa: BLE001
                        self.errors[user] = str(e)[:120]
                    await asyncio.sleep(gap)
