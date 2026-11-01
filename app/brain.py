"""«Мозок» Тривоги: архів усього, що зібрано; навчання маршрутів; навчання довіри до каналів.

- Archive    — SQLite з кожним повідомленням і кожною точкою треку (переживає перезапуск).
- RouteModel — граф переходів «пункт → наступний пункт» для кожного типу цілі, вивчений з треків
               (живих і відтворених з історії каналів). Дає прогноз маршруту, коли канал не назвав куди,
               і оцінку, звідки ціль іде, коли відомо лише «курсом на X».
- Reliability — бета-оцінка точності кожного каналу: підтвердили його повідомлення інші незалежні
               джерела чи ні. Нові канали стартують з апріорної довіри й далі вчаться самі.
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "brain.sqlite"
PRIOR_W = 12.0  # «вага» апріорної довіри в спостереженнях


class Brain:
    def __init__(self, path: Path = DB) -> None:
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=2)
        try:
            self.db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS msg(t REAL, src TEXT, link TEXT, kind TEXT, type TEXT, cnt INT, places TEXT, track TEXT, text TEXT);
                CREATE INDEX IF NOT EXISTS msg_t ON msg(t);
                CREATE TABLE IF NOT EXISTS trans(type TEXT, a TEXT, b TEXT, n REAL, alat REAL, alon REAL, blat REAL, blon REAL, PRIMARY KEY(type, a, b));
                CREATE TABLE IF NOT EXISTS rel(src TEXT PRIMARY KEY, ok REAL, bad REAL);
                CREATE TABLE IF NOT EXISTS seen(link TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS site(type TEXT, site TEXT, entry TEXT, n REAL, PRIMARY KEY(type, site, entry));
                """
            )
        except sqlite3.Error:  # файл зайнятий іншим процесом — працюємо в пам'яті, моніторинг важливіший
            self.db = sqlite3.connect(":memory:", check_same_thread=False)
            self.db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS msg(t REAL, src TEXT, link TEXT, kind TEXT, type TEXT, cnt INT, places TEXT, track TEXT, text TEXT);
                CREATE INDEX IF NOT EXISTS msg_t ON msg(t);
                CREATE TABLE IF NOT EXISTS trans(type TEXT, a TEXT, b TEXT, n REAL, alat REAL, alon REAL, blat REAL, blon REAL, PRIMARY KEY(type, a, b));
                CREATE TABLE IF NOT EXISTS rel(src TEXT PRIMARY KEY, ok REAL, bad REAL);
                CREATE TABLE IF NOT EXISTS seen(link TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS site(type TEXT, site TEXT, entry TEXT, n REAL, PRIMARY KEY(type, site, entry));
                """
            )
        self.trans: dict[str, dict[str, dict[str, list]]] = {}  # type -> a -> b -> [n, blat, blon]
        self.pred: dict[str, dict[str, dict[str, list]]] = {}   # type -> b -> a -> [n, alat, alon]
        for typ, a, b, n, alat, alon, blat, blon in self.db.execute("SELECT * FROM trans"):
            self.trans.setdefault(typ, {}).setdefault(a, {})[b] = [n, blat, blon]
            self.pred.setdefault(typ, {}).setdefault(b, {})[a] = [n, alat, alon]
        self.rel_stats = {s: [ok, bad] for s, ok, bad in self.db.execute("SELECT * FROM rel")}
        self.sites: dict[str, dict[str, dict[str, float]]] = {}  # type -> entry('' = будь-де) -> site -> n
        for typ, site, entry, n in self.db.execute("SELECT * FROM site"):
            self.sites.setdefault(typ, {}).setdefault(entry, {})[site] = n
        self.pending = 0

    # ---------------- архів
    def seen(self, link: str | None) -> bool:
        if not link:
            return False
        with self.lock:
            try:
                cur = self.db.execute("INSERT OR IGNORE INTO seen(link) VALUES(?)", (link,))
                return cur.rowcount == 0
            except sqlite3.Error:
                return False

    def log_msg(self, t, src, link, kind, typ, cnt, places, track, text) -> None:
        with self.lock:
            self._x("INSERT INTO msg VALUES(?,?,?,?,?,?,?,?,?)",
                            (t, src, link, kind, typ, cnt, json.dumps(places, ensure_ascii=False), track, (text or "")[:600]))
            self._tick()

    def _tick(self) -> None:
        self.pending += 1
        if self.pending >= 25:
            try:
                self.db.commit()
            except sqlite3.Error:
                pass
            self.pending = 0

    def _x(self, sql, args=()):
        try:
            self.db.execute(sql, args)
        except sqlite3.Error:
            pass

    def flush(self) -> None:
        with self.lock:
            try:
                self.db.commit()
            except sqlite3.Error:
                pass

    # ---------------- маршрути
    def learn_step(self, typ: str, a, b, w: float = 1.0) -> None:
        """a, b — Place; перехід вчиться лише між різними пунктами на правдоподібній відстані."""
        if a.name == b.name:
            return
        d = math.hypot((a.lat - b.lat) * 111, (a.lon - b.lon) * 73)
        if d < 4 or d > 110:
            return
        row = self.trans.setdefault(typ, {}).setdefault(a.name, {}).setdefault(b.name, [0.0, b.lat, b.lon])
        row[0] += w
        prow = self.pred.setdefault(typ, {}).setdefault(b.name, {}).setdefault(a.name, [0.0, a.lat, a.lon])
        prow[0] += w
        with self.lock:
            self._x(
                "INSERT INTO trans VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(type,a,b) DO UPDATE SET n=n+excluded.n",
                (typ, a.name, b.name, w, a.lat, a.lon, b.lat, b.lon))
            self._tick()

    def next_places(self, typ: str, name: str, heading: float | None = None, here=None) -> list[tuple[str, float, float, float]]:
        """Найімовірніші наступні пункти: [(назва, ймовірність, lat, lon)]. Курс (якщо є) відсікає зворотні напрямки."""
        row = self.trans.get(typ, {}).get(name) or self.trans.get("shahed", {}).get(name) or {}
        items = []
        for b, (n, lat, lon) in row.items():
            w = n
            if heading is not None and here is not None:
                az = (math.degrees(math.atan2((lon - here[1]) * 73, (lat - here[0]) * 111)) + 360) % 360
                diff = abs((az - heading + 180) % 360 - 180)
                if diff > 100:
                    continue
                w *= max(0.15, math.cos(math.radians(diff)))
            items.append((b, w, lat, lon))
        tot = sum(w for _, w, _, _ in items) or 1
        return sorted([(b, w / tot, lat, lon) for b, w, lat, lon in items], key=lambda x: -x[1])[:3]

    def prev_place(self, typ: str, name: str) -> tuple[str, float, float, float] | None:
        """Звідки найчастіше приходять у пункт (для «курсом на X» без поточного місця)."""
        row = self.pred.get(typ, {}).get(name) or self.pred.get("shahed", {}).get(name) or {}
        if not row:
            return None
        tot = sum(v[0] for v in row.values())
        a, (n, lat, lon) = max(row.items(), key=lambda kv: kv[1][0])
        return (a, n / tot, lat, lon) if tot >= 2 else None

    def stats(self) -> dict:
        return {"transitions": sum(len(v) for t in self.trans.values() for v in t.values()),
                "places": len({a for t in self.trans.values() for a in t}),
                "launch_sites": sum(len(v) for t in self.sites.values() for v in t.values())}

    # ---------------- довіра до каналів
    def rel(self, src: str, prior: float) -> float:
        ok, bad = self.rel_stats.get(src, (0.0, 0.0))
        return (prior * PRIOR_W + ok) / (PRIOR_W + ok + bad)

    def rel_update(self, src: str, confirmed: bool, w: float = 1.0) -> None:
        st = self.rel_stats.setdefault(src, [0.0, 0.0])
        st[0 if confirmed else 1] += w
        with self.lock:
            self._x("INSERT INTO rel VALUES(?,?,?) ON CONFLICT(src) DO UPDATE SET ok=excluded.ok, bad=excluded.bad",
                            (src, st[0], st[1]))
            self._tick()

    # ---------------- точки пуску
    def learn_site(self, typ: str, site: str, entry: str | None, w: float = 1.0) -> None:
        """Ціль цього типу стартувала з site (і зайшла через entry, якщо відомо)."""
        for e in {"", entry or ""}:
            row = self.sites.setdefault(typ, {}).setdefault(e, {})
            row[site] = row.get(site, 0.0) + w
            with self.lock:
                self._x("INSERT INTO site VALUES(?,?,?,?) ON CONFLICT(type,site,entry) DO UPDATE SET n=n+excluded.n", (typ, site, e, w))
                self._tick()

    def site_stats(self, typ: str, entry: str | None) -> dict[str, float]:
        m = self.sites.get(typ, {})
        out = {k: v * 0.3 for k, v in m.get("", {}).items()}
        for k, v in m.get(entry or "\0", {}).items():
            out[k] = out.get(k, 0) + v
        return out
