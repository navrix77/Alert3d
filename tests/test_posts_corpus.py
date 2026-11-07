"""Реальні пости, на яких SKY помилявся: кожна помилка стає тестом, щоб не повторювалась (07.11)."""
import pytest

from app.parser import Parser

P = Parser()
# (канал, текст, тип або None, підрядок назви місця або None)
CASES = [
    ("M", "Ударний БПЛА на Нескорених‼️", "shahed", "Нескорених"),
    ("R", "БпЛА появился и упал над Салтовкой", "uav", "Салтівка"),
    ("TLK", "Ударный на СС⚠️", "shahed", "Північна Салтівка"),
    ("TLK", "Ударный на Холодную Гору", "shahed", "Холодна Гора"),
    ("M", "Ударний БПЛА на Салтівку", "shahed", "Салтівка"),
]


@pytest.mark.parametrize("ch,text,typ,place", CASES)
def test_known_posts(ch, text, typ, place):
    o = P.parse(text, ch, (49.99, 36.23))
    assert o.type == typ, o
    if place:
        assert any(place in r.place.name for r in o.places), [r.place.name for r in o.places]


def test_from_place_is_start_not_destination():
    """07.11: «от Слободское на Харьков…» — ціль біля Слободського, а не в центрі Харкова."""
    import time
    import app.main as m
    from app import config
    from app.tracker import Tracker
    t = Tracker(config.SOURCES, m.brain)
    now = time.time()
    m.feed(t, "Молния ⚠️от Слободское на Харьков, Элитное, Горизонт", "ND", now - 30, None, log=False)
    tr = t.snapshot(now)["tracks"][0]
    assert tr["lon"] > 36.38, tr["lon"]  # східніше центру Харкова (36.27)


def test_no_learned_exit_when_over_named_target():
    """07.11: «БпЛА на Харків… над Харковом» — ціль над містом-метою, «ймовірно далі: Коротич» не показуємо."""
    import time
    import app.main as m
    from app import config
    from app.tracker import Tracker
    t = Tracker(config.SOURCES, m.brain)
    now = time.time()
    for dt, k, x in [(-300, "KL", "2х БпЛА курсом на Харків (Харківщина)"), (-60, "MK", "БпЛА над Харковом.")]:
        m.feed(t, x, k, now + dt, None, log=False)
    orig = (m.brain.next_places, m.brain.next_path)
    try:
        m.brain.next_places = lambda *a, **k: [("Коротич", 0.9, 49.89, 36.12)]
        m.brain.next_path = lambda *a, **k: [("Коротич", 0.9, 49.89, 36.12)]
        tr = t.snapshot(now)["tracks"][0]
        assert not tr.get("pred_next") and not tr.get("lpath")
    finally:
        m.brain.next_places, m.brain.next_path = orig


def _tracker():
    import app.main as m
    from app import config
    from app.tracker import Tracker
    return m, Tracker(config.SOURCES, m.brain)


def test_city_target_from_north_is_not_inside_city():
    """07.11: «БпЛА на Харків з півночі» — ціль на підході з півночі, а не в центрі міста."""
    import time
    m, t = _tracker()
    now = time.time()
    for dt, k, x in [(-300, "KL", "2х БпЛА курсом на Харків (Харківщина)"), (-200, "MU", "БпЛА на Харків з півночі.")]:
        m.feed(t, x, k, now + dt, None, log=False)
    tr = t.snapshot(now)["tracks"][0]
    assert tr["lat"] > 50.03, tr["lat"]  # північніше центру Харкова (49.99)
    # підтвердження «над Харковом» — ціль у центрі
    m.feed(t, "БпЛА над Харковом.", "MK", now - 20, None, log=False)
    tr = t.snapshot(now)["tracks"][0]
    assert abs(tr["lat"] - 49.992) < 0.04, tr["lat"]


def test_fpv_and_shahed_same_spot_merge():
    """07.11: FPV і шахед в одній точці від різних каналів — один об'єкт."""
    import time
    m, t = _tracker()
    now = time.time()
    m.feed(t, "FPV курсом на П'ятихатки", "M", now - 120, None, log=False)
    m.feed(t, "Шахед курсом на П'ятихатки", "TLK", now - 100, None, log=False)
    assert len(t.snapshot(now)["tracks"]) == 1


def test_named_targets_only_fly_inbound_not_to_border():
    """07.11: «на П'ятихатки → на Лісне → курсом на Лесное» без позиції — носом від кордону, а не на північ до нього."""
    import time
    m, t = _tracker()
    now = time.time()
    for dt, k, x in [(-200, "M", "Ударний БПЛА на П'ятихатки‼️"), (-120, "M", "Ударний БПЛА на Лісне⚠️"), (-30, "CX", "🟧 Ударный курсом на Лесное")]:
        m.feed(t, x, k, now + dt, None, log=False)
    hd = t.snapshot(now)["tracks"][0]["hd"]
    assert hd is not None and 90 < hd < 270, hd  # на південь, до міста


def test_banderol_course_from_origin_oblast():
    """07.11: «курсом на Диканьку, Полтавщина з Харківщини» — курс від Харківщини (на захід), а не на північ."""
    import time
    m, t = _tracker()
    now = time.time()
    m.feed(t, "⚠ 1х малогабаритна крилата ракета Бандероль курсом на Диканьку, Полтавщина з Харківщини.", "UR", now - 240, None, log=False)
    hd = t.snapshot(now)["tracks"][0]["hd"]
    assert hd is not None and 240 < hd < 320, hd


def test_launch_zone_fallback_banderol():
    """Бандероль без курсу: від найближчої зони пуску (Білгородщина) на південний захід, не на північ."""
    import time
    m, t = _tracker()
    now = time.time()
    m.feed(t, "1х Бандероль курсом на Харків", "UR", now - 60, None, log=False)
    hd = t.snapshot(now)["tracks"][0]["hd"]
    assert hd is not None and 120 < hd < 280, hd


def test_launch_zones_reach():
    from app.launch_zones import nearest
    assert nearest("banderol", 49.9, 36.2)[2].startswith(("Білгород", "Курськ"))
    assert nearest("banderol", 50.4, 30.5) is None or nearest("banderol", 50.4, 30.5)[3] <= 520


@pytest.mark.parametrize("text,side,course", [
    ("БпЛА на Харків з півночі.", 0.0, 180.0),
    ("Шахед на Харків зі сходу", 90.0, 270.0),
    ("на Харків з півдня", 180.0, 0.0),
])
def test_approach_side(text, side, course):
    o = P.parse(text, "MU", None)
    assert o.side == side and o.course == course
