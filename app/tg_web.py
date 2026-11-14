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
TEXT = re.compile(r'<div class="tgme_widget_message_text(?![^"]*js-message_reply_text)[^"]*"[^>]*>(.*?)</div>', re.S)  # 08.11: не текст цитованого повідомлення (reply-прев'ю)
REPLYQ = re.compile(r'<div class="tgme_widget_message_text js-message_reply_text"[^>]*>(.*?)</div>', re.S)
TIME = re.compile(r'<time[^>]*datetime="([^"]+)"')
# зображення поста (мапа зі стрілками, схема): t.me/s віддає його як background-image (03.11 — для моделі із зором)
PHOTO = re.compile(r"tgme_widget_message_photo_wrap[^>]*background-image:url\('([^']+)'\)")
PHOTOS: dict[str, str] = {}
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
        ph = PHOTO.search(body)
        if ph:
            PHOTOS[f"https://t.me/{_ch}/{mid}"] = ph.group(1)
            if len(PHOTOS) > 3000:
                for k in list(PHOTOS)[:1000]:
                    PHOTOS.pop(k, None)
        txt = _clean(x.group(1))
        q = REPLYQ.search(body)
        # 14.11: відповідь, що сама називає тип («Ударний на Лісне/Місто❗️» у відповідь на «Ударний на Борщову/Руські Тишки», monitor1654),
        # самодостатня: цитата повертала ціль на старе місце й розвертала курс до кордону
        if q and len(txt) <= 40 and not SELF_TYPE.search(txt.lower()):  # 08.11: короткий коментар-відповідь («Впав», «Далі Веселе») без місця стосується цитованої цілі — підставляємо її
            qt = _clean(q.group(1)).replace("\n", " ")
            if qt:
                txt = f"{qt[:160]} — {txt}"
        out.append((int(mid), ts, txt))
    return out


SELF_TYPE = re.compile(r"ударн|удар\b|шахед|шахід|герань|реактив|бпла|бпл\b|дрон|ракет|каб\b|каби|молн|ланцет|fpv|фпв|мопед|балліст|баліст|крилат|бандерол|ударный|ударные")


class WebMonitor:
    def __init__(self) -> None:
        self.last_id: dict[str, int] = {}
        self.last_ok: dict[str, float] = {}
        self.errors: dict[str, str] = {}

    @staticmethod
    def photo(link: str) -> str | None:
        return PHOTOS.get(link)

    def state(self) -> dict:
        now = time.time()
        live = [u for u, t in self.last_ok.items() if now - t < 420]
        return {"channels": len(config.CHANNELS), "live": len(live), "errors": dict(list(self.errors.items())[:5]),
                "cycle": round(getattr(self, "cycle", 0), 1), "fast_every": config.TG_WEB_CYCLE_SEC,
                "all_every": round(getattr(self, "full_rotation", 0))}

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
            try:
                on_message(text, key, ts, f"https://t.me/{user}/{mid}")
            except Exception:  # одне «погане» повідомлення не має зупиняти моніторинг
                log.exception("помилка обробки поста %s/%s", user, mid)
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
            # УСІ канали, не лише головні: інакше решта дочитується порціями вже після старту, старі пости
            # приходять не за часом і створюють зайві «нові» цілі (02.11, перезапуск під час атаки: 29 → 87 шахедів)
            buf = []
            sem0 = asyncio.Semaphore(6)

            async def first(key, user):
                async with sem0:
                    try:
                        r = await cli.get(f"https://t.me/s/{user}")
                        msgs = parse_page(r.text)
                        self.last_ok[user] = time.time()
                        self.last_id[user] = max((m[0] for m in msgs), default=0)
                        buf.extend((ts, text, key, f"https://t.me/{user}/{mid}") for mid, ts, text in msgs if ts > time.time() - 1800)
                    except Exception as e:  # noqa: BLE001
                        self.errors[user] = str(e)[:120]
                    await asyncio.sleep(0.25)
            await asyncio.gather(*(first(k, u) for k, u in chans))
            for ts, text, key, link in sorted(buf):
                try:
                    on_message(text, key, ts, link)
                except Exception:
                    log.exception("помилка обробки поста %s", link)
            log.info("t.me/s: стартово прочитано %d постів; усього каналів у моніторингу: %d", len(buf), len(chans))
            # Далі — безперервно: усі головні канали щоцикла, решта — широкими порціями; паралельно по 6 запитів
            fast = [(k, u) for k, u in chans if k in config.FAST]
            slow = [(k, u) for k, u in chans if k not in config.FAST]
            per_cycle_slow = 45
            conc = 10  # адаптивно: при 429 знижуємо, чисті цикли повертають до максимуму
            sem = asyncio.Semaphore(conc)
            si = 0

            async def one(key, user):
                async with sem:
                    try:
                        await self.poll(cli, key, user, on_message, 1800)
                    except httpx.HTTPStatusError as e:
                        self.errors[user] = f"HTTP {e.response.status_code}"
                        if e.response.status_code == 429:
                            self.backoff = time.time() + 30
                            self._hit429 = True
                    except Exception as e:  # noqa: BLE001
                        self.errors[user] = str(e)[:120]

            while True:
                t0 = time.time()
                if len(config.CHANNELS) != len(chans):  # автопошук додав нові джерела — підхоплюємо без перезапуску
                    chans = [(k, u) for k, u, *_ in config.CHANNELS]
                    slow = [(k, u) for k, u in chans if k not in config.FAST]
                if time.time() < getattr(self, "backoff", 0):
                    await asyncio.sleep(5)
                    continue
                if getattr(self, "_hit429", False):  # резервний режим: м'якший темп, доки Telegram не заспокоїться
                    self._hit429 = False
                    per_cycle_slow, conc = max(15, int(per_cycle_slow * 0.6)), max(4, conc - 3)
                    sem = asyncio.Semaphore(conc)
                    log.warning("t.me/s: 429 → знижую темп (порція %d, паралельно %d)", per_cycle_slow, conc)
                elif per_cycle_slow < 45 and time.time() > getattr(self, "backoff", 0) + 60:
                    per_cycle_slow, conc = min(45, per_cycle_slow + 5), min(10, conc + 1)
                    sem = asyncio.Semaphore(conc)
                batch = fast + [slow[(si + n) % len(slow)] for n in range(min(per_cycle_slow, len(slow)))]
                si = (si + per_cycle_slow) % max(1, len(slow))
                await asyncio.gather(*(one(k, u) for k, u in batch))
                self.cycle = time.time() - t0
                self.full_rotation = (len(slow) / per_cycle_slow) * max(config.TG_WEB_CYCLE_SEC, self.cycle)
                await asyncio.sleep(max(1.0, config.TG_WEB_CYCLE_SEC - self.cycle))
