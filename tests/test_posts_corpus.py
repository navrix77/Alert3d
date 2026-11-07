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
