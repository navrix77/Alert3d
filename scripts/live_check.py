"""Перевірка живого сервера по публічних ендпоїнтах (без доступу до VM): python scripts/live_check.py [URL]
Код виходу 1, якщо знайдено проблему. Можна запускати з Cloud Shell або з cron."""
import json
import sys
import time
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://sky.navryx.com.ua").rstrip("/")


def get(p):
    with urllib.request.urlopen(BASE + p, timeout=25) as r:
        return r.read().decode()


bad = []
h = json.loads(get("/api/health"))
if not h.get("ok") or h.get("problems"):
    bad.append(f"health: {h.get('problems')}")
if (h.get("channels_live") or 0) < 0.8:
    bad.append(f"канали живі лише {h.get('channels_live')}")
if (h.get("msg_age") or 0) > 900:
    bad.append(f"останнє повідомлення {h['msg_age']} с тому")
s = json.loads(get("/api/state"))
now = s.get("now") or time.time()
for t in s.get("tracks", []):
    if t["first"] > t["last"]:
        bad.append(f"{t['id']}: first>last")
    if not (43 <= t["lat"] <= 53 and 21 <= t["lon"] <= 41):
        bad.append(f"{t['id']}: координати поза межами")
sw = get("/sw.js")
print("build:", sw.split("tryvoga-v")[1][:3], "| tracks:", len(s.get("tracks", [])), "| msg_age:", h.get("msg_age"))
print("OK" if not bad else "ПРОБЛЕМИ:\n- " + "\n- ".join(bad))
sys.exit(1 if bad else 0)
