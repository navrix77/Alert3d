"""Одноразово запустити НА СВОЄМУ КОМП'ЮТЕРІ, щоб отримати рядок сесії Telethon.

    pip install telethon
    python scripts/telegram_login.py

Введи api_id, api_hash (https://my.telegram.org → API development tools), номер телефону окремого
акаунта та код з Telegram. Скрипт надрукує TG_SESSION — поклади його в Secret Manager, нікому не пересилай.
Акаунт лише читає публічні канали; підпишись на них у цьому акаунті."""
import asyncio

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    api_id = int(input("api_id: ").strip())
    api_hash = input("api_hash: ").strip()
    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        me = await client.get_me()
        print(f"\nУвійшли як {me.first_name} (@{me.username})")
        print("\nTG_SESSION=" + client.session.save())


asyncio.run(main())
