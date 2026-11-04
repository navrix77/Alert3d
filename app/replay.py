"""Демо без Telegram: прокручує записану ніч 29→30.10.2026 так, ніби вона йде зараз.
Вмикається змінною REPLAY=1 (REPLAY_SPEED, у скільки разів швидше)."""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from .geo import Place
from .parser import Observation, PlaceRef

TYMAP = {"S": "shahed", "J": "jet", "M": "molniya", "C": "cruise", "B": "ballistic", "K": "kab"}
CH = {"D": "Nablydatel_Dozor", "M": "monitor1654", "R": "radar_kharkov", "K": "kpszsu"}
FILE = Path(__file__).resolve().parent.parent / "tests" / "night_2026-10-29.json"


async def run(tracker) -> None:
    if os.getenv("REPLAY") != "1":
        return
    speed = float(os.getenv("REPLAY_SPEED", "1"))
    start_min = float(os.getenv("REPLAY_FROM_MIN", "360"))
    d = json.loads(FILE.read_text(encoding="utf-8"))
    places = [Place(n, la, lo, "C") for n, la, lo in d["places"]]
    while True:
        t_real0 = time.time()
        recs = [r for r in d["recs"] if r[0] >= start_min - 40]
        for t, s, mid, ty, cnt, fl, pl in recs:
            due = t_real0 + (t - start_min) * 60 / speed
            if due > time.time():
                await asyncio.sleep(due - time.time())
            refs = [PlaceRef(r, places[v]) for r, v in pl if places[v].name != "Харківщина"]
            o = Observation(type=TYMAP.get(ty), count=cnt or None, places=refs, close="x" in fl, safety="p" in fl, aviation="a" in fl)
            # час подій «перекладаємо» в теперішнє, швидкість цілей — множимо, щоб рух був видимий
            tracker.ingest(o, s, due if speed == 1 else time.time(), f"https://t.me/{CH[s]}/{mid}")
        await asyncio.sleep(30)
