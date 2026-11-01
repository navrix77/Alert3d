"""Налаштування з оточення (Cloud Run: змінні та Secret Manager)."""
from __future__ import annotations

import os

from .tracker import Source

TG_API_ID = int(os.getenv("TG_API_ID", "0") or 0)
TG_API_HASH = os.getenv("TG_API_HASH", "")
TG_SESSION = os.getenv("TG_SESSION", "")  # StringSession, створюється scripts/telegram_login.py
ALERTS_TOKEN = os.getenv("ALERTS_IN_UA_TOKEN", "")  # https://alerts.in.ua/api-request
ALERTS_POLL_SEC = int(os.getenv("ALERTS_POLL_SEC", "15"))
PUSH_SEC = float(os.getenv("PUSH_SEC", "2"))
MAP_STYLE_VECTOR = os.getenv("MAP_STYLE_VECTOR", "https://tiles.openfreemap.org/styles/liberty")
MAPTILER_KEY = os.getenv("MAPTILER_KEY", "")

# Вайтлист каналів: ключ -> (username, назва, апріорна довіра, офіційний)
CHANNELS = [
    ("K", "kpszsu", "Повітряні Сили ЗСУ", 0.95, True),
    ("D", "Nablydatel_Dozor", "Наблюдатель · Ночной Дозор", 0.80, False),
    ("M", "monitor1654", "monitor 1654", 0.80, False),
    ("R", "radar_kharkov", "Радар Харків", 0.70, False),
]
extra = os.getenv("TG_CHANNELS_EXTRA", "")  # "key:username:Назва:0.7,..."
for item in filter(None, extra.split(",")):
    k, u, n, r = item.split(":")
    CHANNELS.append((k, u, n, float(r), False))

SOURCES = {k: Source(k, n, r, off, f"https://t.me/{u}") for k, u, n, r, off in CHANNELS}
BY_USERNAME = {u.lower(): k for k, u, *_ in CHANNELS}
