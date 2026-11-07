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
