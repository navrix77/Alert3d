"""«Куди летіли наші дрони»: регіони РФ, над якими, за офіційними заявами МО РФ, «збивали українські БпЛА».

Лише зведені постфактум повідомлення (регіон + кількість), без живих траєкторій — це новинний шар, а не трекер.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

import httpx

from .tg_web import UA, parse_page

log = logging.getLogger("ru")
CHANNEL = "mod_russia"
REGIONS = [  # основа російської назви → (українська назва, lat, lon)
    ("белгородск", "Бєлгородська обл.", 50.6, 36.6), ("курск", "Курська обл.", 51.7, 36.2), ("брянск", "Брянська обл.", 53.2, 34.4),
    ("воронежск", "Воронезька обл.", 51.7, 39.2), ("орловск", "Орловська обл.", 52.97, 36.07), ("тульск", "Тульська обл.", 54.2, 37.6),
    ("калужск", "Калузька обл.", 54.5, 36.3), ("смоленск", "Смоленська обл.", 54.8, 32.0), ("московского региона", "Москва й область", 55.75, 37.6),
    ("московск", "Московська обл.", 55.6, 37.9), ("рязанск", "Рязанська обл.", 54.6, 39.7), ("липецк", "Липецька обл.", 52.6, 39.6),
    ("тамбовск", "Тамбовська обл.", 52.7, 41.4), ("ростовск", "Ростовська обл.", 47.5, 40.5), ("краснодарск", "Краснодарський край", 45.0, 39.0),
    ("нижегородск", "Нижньогородська обл.", 56.3, 44.0), ("саратовск", "Саратовська обл.", 51.5, 46.0), ("волгоградск", "Волгоградська обл.", 48.7, 44.5),
    ("пензенск", "Пензенська обл.", 53.2, 45.0), ("татарстан", "Татарстан", 55.8, 49.1), ("чуваш", "Чувашія", 56.1, 47.2),
    ("марий эл", "Марій Ел", 56.6, 47.9), ("мордови", "Мордовія", 54.2, 45.2), ("самарск", "Самарська обл.", 53.2, 50.1),
    ("ленинградск", "Ленінградська обл.", 59.9, 30.3), ("псковск", "Псковська обл.", 57.8, 28.3), ("новгородск", "Новгородська обл.", 58.5, 31.3),
    ("тверск", "Тверська обл.", 56.86, 35.9), ("ярославск", "Ярославська обл.", 57.6, 39.9), ("владимирск", "Владимирська обл.", 56.1, 40.4),
    ("ивановск", "Іванівська обл.", 57.0, 41.0), ("астраханск", "Астраханська обл.", 46.35, 48.0), ("калмык", "Калмикія", 46.3, 44.3),
    ("ставропольск", "Ставропольський край", 45.0, 42.0), ("республики крым", "Крим (окупований)", 45.2, 34.2),
    ("азовского моря", "Азовське море", 46.0, 37.0), ("черного моря", "Чорне море", 44.0, 33.5), ("курской", "Курська обл.", 51.7, 36.2),
]
SUMMARY = re.compile(r"(?:уничтожен|перехвачен|сбит)\w*\s+(\d+)\s+(?:украинск\w+\s+)?беспилотн", re.I)
PER = re.compile(r"(\d+)\s*[–—-]\s*над\s+(?:территори|акватори)\w+\s+([^,;.]+)", re.I)


def parse(text: str) -> dict | None:
    t = text.lower().replace("ё", "е")
    m = SUMMARY.search(t)
    if not m or "над территори" not in t and "над акватори" not in t:
        return None
    regs: dict[str, dict] = {}
    for cnt, chunk in PER.findall(t):
        for stem, uk, la, lo in REGIONS:
            if stem in chunk:
                regs[uk] = {"n": uk, "lat": la, "lon": lo, "cnt": int(cnt)}
                break
    if not regs:
        tail = t[m.end():]
        for stem, uk, la, lo in REGIONS:
            if stem in tail and uk not in regs:
                regs[uk] = {"n": uk, "lat": la, "lon": lo, "cnt": None}
                tail = tail.replace(stem, " ")  # «Московского региона» не рахуємо вдруге як «Московскую область»
    period = re.search(r"(в течение (?:дня|ночи|суток)|прошедшей ночью|в период с [^,]+?мск)", t)
    return {"total": int(m.group(1)), "regions": list(regs.values()), "period": period.group(1) if period else None} if regs else None


class RuStrikes:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.seen: set[str] = set()

    def state(self) -> list[dict]:
        now = time.time()
        return [e for e in self.events if now - e["t"] < 24 * 3600]

    async def run(self) -> None:
        async with httpx.AsyncClient(timeout=20, headers=UA, follow_redirects=True) as cli:
            while True:
                try:
                    r = await cli.get(f"https://t.me/s/{CHANNEL}")
                    for mid, ts, text in parse_page(r.text):
                        link = f"https://t.me/{CHANNEL}/{mid}"
                        if link in self.seen:
                            continue
                        self.seen.add(link)
                        ev = parse(text)
                        if ev:
                            ev.update(t=ts, link=link)
                            self.events.append(ev)
                    self.events = self.state()
                except Exception as e:  # noqa: BLE001
                    log.warning("ru strikes: %s", e)
                await asyncio.sleep(120)
