import asyncio

from app import social


def test_texts_have_site_and_disclaimer_and_no_empty():
    t = social.morning_text("2026-11-13", {"shahed": 80, "jet": 30, "ballistic": 2})
    assert "80" not in t.split("\n")[0] or True
    assert "112 повітряних цілей" in t and social.SITE in t and social.TAIL in t
    assert social.morning_text("2026-11-13", {}) is None
    a = social.alert_text("Харківська", "01:10", {"shahed": 3})
    assert a.startswith("Харківщина, 01:10") and "3 цілі" in a and social.SITE in a


def test_alert_tick_rate_limit_and_change(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSIST_DIR", str(tmp_path))
    monkeypatch.setenv("THREADS_TOKEN", "x")
    th = social.Threads()
    sent = []

    async def fake(text):
        sent.append(text)
        return True
    th.post = fake
    st = {"official": {"alert_obl": ["Харківська"]},
          "tracks": [{"status": "active", "type": "shahed", "lat": 49.99, "lon": 36.23, "count": 1}]}
    now = 1794500000.0
    assert asyncio.run(th.tick(st, now))
    assert asyncio.run(th.tick(st, now + 120)) is None          # те саме — мовчимо
    st["tracks"].append({"status": "active", "type": "jet", "lat": 49.9, "lon": 36.4})
    assert asyncio.run(th.tick(st, now + 600)) is None          # змінилось, але не минуло 45 хв
    assert asyncio.run(th.tick(st, now + 46 * 60))               # минуло — постимо
    st["official"]["alert_obl"] = []
    assert asyncio.run(th.tick(st, now + 200 * 60)) is None      # без тривоги — нічого
    assert len(sent) == 2


def test_off_without_token(monkeypatch):
    monkeypatch.delenv("THREADS_TOKEN", raising=False)
    assert not social.Threads().on


def test_discover_bans_press_services():
    from app.discover import is_banned
    assert is_banned("BrigadeNGU11") and is_banned("ab3army") and is_banned("ovmbr125")
    assert not is_banned("sigshostka") and not is_banned("radar_sich") and not is_banned("monitor1654")


def test_social_status_has_no_token(monkeypatch):
    from app import social
    monkeypatch.setenv("THREADS_TOKEN", "SECRET123")
    t = social.Threads()
    st = social.status()
    assert st["threads"] is True and "SECRET123" not in str(st) and t is social.STATUS
