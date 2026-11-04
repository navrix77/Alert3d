"""Вивантаження даних сервера в гілку `ops-data` репозиторію GitHub (для сесій самоосвіти й аналізу).

Навіщо: хмарні сесії не завжди можуть звернутися до sky.navryx.com.ua (проксі), а до GitHub можуть. Тому сервер сам
щогодини кладе в окрему гілку те, на чому працюють бектест і самоаналіз:
  journal-72h.json.gz   журнал повідомлень каналів за 72 год (формат scripts/backtest.py: t, src, link, kind, type, places, track, text)
  selfcheck.json        щоденний самоаналіз сервера (scripts/selfcheck.py на повній базі)
  fusion.json, fc_calib_live.json, occupied.geojson  якщо є
  status.json           час, коміт сервера, кількість повідомлень про цілі за останню годину (ознака масованої атаки)

Лише публічні повідомлення каналів і похідні звіти; бази push, візитів, ключі й .env НЕ вивантажуються.
Гілка — один коміт без історії (force push), тож репозиторій не росте. `main` не чіпається, оновлення сервера не запускає.
Вмикається змінною OPS_GIT_TOKEN у /opt/navryx/.env (fine-grained токен GitHub: лише цей репозиторій, Contents: write).
OPS_GIT_REPO (типово navrix77/Alert3d), OPS_EXPORT_MIN (типово 60), OPS_EXPORT_HOURS (типово 72).
"""
from __future__ import annotations

import asyncio
import base64
import gzip
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

log = logging.getLogger("tryvoga.ops")
ROOT = Path(__file__).resolve().parent.parent
BRANCH = "ops-data"
EXTRA = ("selfcheck.json", "fusion.json", "fc_calib_live.json", "occupied.geojson")
TARGET_KINDS = ("track", "zone", "close")


def collect(db, lock, out: Path, hours: float = 72, now: float | None = None) -> dict:
    """Пише файли вивантаження в out; повертає status."""
    now = now or time.time()
    with lock:
        rows = db.execute("SELECT t, src, link, kind, type, places, track, text FROM msg WHERE t > ? ORDER BY t",
                          (now - hours * 3600,)).fetchall()
        last_h = db.execute(f"SELECT count(*) FROM msg WHERE t > ? AND kind IN ({','.join('?' * len(TARGET_KINDS))})",
                            (now - 3600, *TARGET_KINDS)).fetchone()[0]
    with gzip.open(out / "journal-72h.json.gz", "wt", encoding="utf-8") as f:
        json.dump([list(r) for r in rows], f, ensure_ascii=False)
    for name in EXTRA:
        p = ROOT / "data" / name
        if p.exists():
            shutil.copyfile(p, out / name)
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        commit = ""
    st = {"t": int(now), "utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now)), "hours": hours, "rows": len(rows),
          "targets_last_hour": last_h, "massive": last_h > 100, "server_commit": commit,
          "files": sorted(p.name for p in out.iterdir())}
    (out / "status.json").write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    return st


def _git_env(token: str) -> dict:
    """Токен іде заголовком через змінні середовища git, а не в URL чи аргументах (не видно в ps і логах)."""
    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_CONFIG_COUNT="1",
               GIT_CONFIG_KEY_0="http.https://github.com/.extraheader", GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {auth}",
               GIT_AUTHOR_NAME="NAVRYX SKY server", GIT_AUTHOR_EMAIL="server@sky.navryx.com.ua",
               GIT_COMMITTER_NAME="NAVRYX SKY server", GIT_COMMITTER_EMAIL="server@sky.navryx.com.ua")
    return env


def push(out: Path, token: str, repo: str, msg: str) -> None:
    env = _git_env(token)

    def g(*a):
        r = subprocess.run(["git", *a], cwd=out, env=env, capture_output=True, text=True, timeout=180)
        if r.returncode:
            raise RuntimeError(f"git {a[0]}: {(r.stderr or r.stdout)[-300:].replace(token, '***')}")
    g("init", "-q", "-b", BRANCH)
    g("add", "-A")
    g("commit", "-q", "-m", msg)
    url = repo if "://" in repo else f"https://github.com/{repo}.git"
    g("push", "-q", "--force", url, f"HEAD:refs/heads/{BRANCH}")


def export_once(brain, token: str | None = None, repo: str | None = None, hours: float | None = None) -> dict:
    token = token or os.getenv("OPS_GIT_TOKEN", "")
    repo = repo or os.getenv("OPS_GIT_REPO", "navrix77/Alert3d")
    hours = hours or float(os.getenv("OPS_EXPORT_HOURS", "72"))
    with tempfile.TemporaryDirectory(prefix="ops-") as d:
        out = Path(d)
        st = collect(brain.db, brain.lock, out, hours)
        if token:
            push(out, token, repo, f"Дані сервера {st['utc']} UTC: {st['rows']} повідомлень, цілей за годину {st['targets_last_hour']}")
        return st


async def run(brain) -> None:
    if not os.getenv("OPS_GIT_TOKEN"):
        log.info("ops-data: OPS_GIT_TOKEN не задано, вивантаження в GitHub вимкнено")
        return
    every = max(15.0, float(os.getenv("OPS_EXPORT_MIN", "60"))) * 60
    await asyncio.sleep(120)
    while True:
        try:
            st = await asyncio.to_thread(export_once, brain)
            log.info("ops-data: вивантажено %s повідомлень", st["rows"])
        except Exception as e:  # noqa: BLE001
            log.warning("ops-data: %s", str(e).replace(os.getenv("OPS_GIT_TOKEN", "") or "\0", "***"))
        await asyncio.sleep(every)
