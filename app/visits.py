"""Лічильник відвідувань без cookies і без збереження IP.

Унікальний відвідувач за добу = хеш (сіль доби + IP + User-Agent). Сіль випадкова й живе лише добу:
після зміни доби старі хеші видаляються, лишаються тільки числа, відновити, хто заходив, неможливо.
Перегляд = відкриття сторінки (/, /analysis.html, /daily.html …). «Онлайн», живі підключення до мапи (WebSocket).
"""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

_DIR = Path(os.getenv("PERSIST_DIR") or Path(__file__).resolve().parent.parent / "data")
PAGES = {"/", "/index.html", "/analysis.html", "/daily.html", "/ar.html"}
PAGES |= {"/jak.html", "/about.html"} | {f"/oblast/{s}.html" for s in ("kharkiv", "kyiv", "sumy", "dnipro", "zaporizhzhia", "odesa", "poltava", "chernihiv", "mykolaiv", "kherson", "lviv", "kryvyi-rih")}  # 13.11: сторінки для пошуку теж рахуємо
BOTS = ("bot", "spider", "crawl", "preview", "curl", "python-requests", "httpx", "uptime", "monitor", "headless")


def _day(ts: float | None = None) -> str:
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/Kyiv")
    except Exception:  # noqa: BLE001
        tz = timezone(timedelta(hours=2))
    return (datetime.fromtimestamp(ts, tz) if ts else datetime.now(tz)).strftime("%Y-%m-%d")


class Visits:
    def __init__(self, path: Path | None = None) -> None:
        self.lock = threading.Lock()
        self.db = sqlite3.connect(str(path or _DIR / "visits.sqlite"), check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS day(d TEXT PRIMARY KEY, uniq INT DEFAULT 0, views INT DEFAULT 0, ws INT DEFAULT 0, peak_online INT DEFAULT 0);
            CREATE TABLE IF NOT EXISTS seen(d TEXT, h TEXT, PRIMARY KEY(d, h));
            CREATE TABLE IF NOT EXISTS salt(d TEXT PRIMARY KEY, s TEXT);
        """)
        for col in ("app_uniq", "installs"):  # запуски встановленого застосунку (з іконки) і нові встановлення
            try:
                self.db.execute(f"ALTER TABLE day ADD COLUMN {col} INT DEFAULT 0")
            except sqlite3.OperationalError:
                pass
        self.db.commit()

    def app_hit(self, ip: str | None, ua: str | None, kind: str, ts: float | None = None) -> None:
        """kind='app': запуск з іконки на екрані (унікальний пристрій за добу); 'install': браузер повідомив про встановлення."""
        if not ip or kind not in ("app", "install") or any(b in (ua or "").lower() for b in BOTS):
            return
        d = _day(ts)
        with self.lock:
            h = "a" + hashlib.sha256((self._salt(d) + kind + "|" + ip + "|" + (ua or "")).encode()).hexdigest()[:19]
            self.db.execute("INSERT OR IGNORE INTO day(d) VALUES(?)", (d,))
            new = self.db.execute("INSERT OR IGNORE INTO seen VALUES(?,?)", (d, h)).rowcount
            if new:
                self.db.execute(f"UPDATE day SET {'app_uniq' if kind == 'app' else 'installs'}={'app_uniq' if kind == 'app' else 'installs'}+1 WHERE d=?", (d,))
            self.db.commit()

    def _salt(self, d: str) -> str:
        r = self.db.execute("SELECT s FROM salt WHERE d=?", (d,)).fetchone()
        if r:
            return r[0]
        s = secrets.token_hex(16)
        self.db.execute("INSERT INTO salt VALUES(?,?)", (d, s))
        # минулі доби: лише числа, без хешів і солі
        self.db.execute("DELETE FROM seen WHERE d<?", (d,))
        self.db.execute("DELETE FROM salt WHERE d<?", (d,))
        return s

    def hit(self, ip: str | None, ua: str | None, kind: str = "view", ts: float | None = None) -> None:
        if not ip or any(b in (ua or "").lower() for b in BOTS):
            return
        d = _day(ts)
        with self.lock:
            h = hashlib.sha256((self._salt(d) + ip + "|" + (ua or "")).encode()).hexdigest()[:20]
            self.db.execute("INSERT OR IGNORE INTO day(d) VALUES(?)", (d,))
            new = self.db.execute("INSERT OR IGNORE INTO seen VALUES(?,?)", (d, h)).rowcount
            self.db.execute(f"UPDATE day SET uniq=uniq+?, {'views' if kind == 'view' else 'ws'}={'views' if kind == 'view' else 'ws'}+1 WHERE d=?", (new, d))
            self.db.commit()

    def online(self, n: int) -> None:
        d = _day()
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO day(d) VALUES(?)", (d,))
            self.db.execute("UPDATE day SET peak_online=MAX(peak_online, ?) WHERE d=?", (n, d))
            self.db.commit()

    def stats(self, days: int = 30) -> dict:
        with self.lock:
            rows = self.db.execute("SELECT d, uniq, views, ws, peak_online, COALESCE(app_uniq,0), COALESCE(installs,0) FROM day ORDER BY d DESC LIMIT ?", (days,)).fetchall()
        rows = rows[::-1]
        return {"days": [{"day": d, "visitors": u, "views": v, "map_sessions": w, "peak_online": p, "app_users": a, "installs": i} for d, u, v, w, p, a, i in rows],
                "total_installs": sum(r[6] for r in rows),
                "today": rows[-1][1] if rows and rows[-1][0] == _day() else 0,
                "total_visitor_days": sum(r[1] for r in rows), "total_views": sum(r[2] for r in rows)}
