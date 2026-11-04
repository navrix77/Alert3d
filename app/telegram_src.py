"""Живий потік з публічних Telegram-каналів через Telethon (user-сесія, тільки читання)."""
from __future__ import annotations

import logging

from . import config

log = logging.getLogger("telegram")


async def run(on_message) -> None:
    """on_message(text, source_key, timestamp, link) викликається на кожен новий пост."""
    if not (config.TG_API_ID and config.TG_API_HASH and config.TG_SESSION):
        log.warning("Telegram не налаштовано (TG_API_ID / TG_API_HASH / TG_SESSION)")
        return
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(config.TG_SESSION), config.TG_API_ID, config.TG_API_HASH)
    await client.start()
    chats = [u for _, u, *_ in config.CHANNELS]

    @client.on(events.NewMessage(chats=chats))
    async def handler(ev):
        chat = await ev.get_chat()
        uname = (getattr(chat, "username", "") or "").lower()
        key = config.BY_USERNAME.get(uname)
        if not key or not ev.raw_text:
            return
        link = f"https://t.me/{chat.username}/{ev.id}"
        on_message(ev.raw_text, key, ev.date.timestamp(), link)

    # «Догнати» останні 30 хв після рестарту, щоб треки не обнулялися
    import time

    since = time.time() - 1800
    buf = []
    for u in chats:
        try:
            async for m in client.iter_messages(u, limit=80):
                if m.date.timestamp() < since:
                    break
                if m.raw_text:
                    buf.append((m.date.timestamp(), m.raw_text, config.BY_USERNAME[u.lower()], f"https://t.me/{u}/{m.id}"))
        except Exception as e:
            log.warning("backfill %s: %s", u, e)
    for ts, text, key, link in sorted(buf):
        on_message(text, key, ts, link)
    log.info("Telegram: слухаю %d каналів", len(chats))
    await client.run_until_disconnected()
