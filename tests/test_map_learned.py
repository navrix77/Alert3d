"""11.11: мапа без маршруту від каналів зсуває ціль уздовж навченого ланцюжка, а не прямо за курсом."""
from app.geo import Place, bearing, dist_km, to_xy
from app.tracker import Point, Track, map_xy


class _Brain:
    def next_path(self, typ, name, hd, ll, steps=4):
        # Прилуки → Пирятин (на південь-схід), а курс трека — на захід
        return [("Пирятин", 0.6, 50.24, 32.51)]


def _track(place, t0, est=False):
    x, y = to_xy(place.lat, place.lon)
    tr = Track(id="РБ-1", type="jet", speed=450, heading=270.0)
    tr.obs.append(Point(t0, x, y, "D", place.name, None, place, est))
    return tr


def test_noroute_moves_along_learned_chain():
    pr = Place("Прилуки", 50.594, 32.387, "M", 50000)
    tr = _track(pr, 1000.0)
    a = (tr.last.x, tr.last.y)
    p = map_xy(tr, 1000.0 + 300, _Brain())
    goal = to_xy(50.24, 32.51)
    assert dist_km(a, p) > 5
    assert abs(bearing(a, p) - bearing(a, goal)) < 5
    # без «мозку» — як раніше, за курсом на захід
    q = map_xy(tr, 1000.0 + 300, None)
    assert 260 < bearing(a, q) < 280


def test_at_named_goal_not_moved_out():
    pr = Place("Прилуки", 50.594, 32.387, "M", 50000)
    tr = _track(pr, 1000.0)
    tr.tnames = {"Прилуки"}
    p = map_xy(tr, 1000.0 + 300, _Brain())
    q = map_xy(tr, 1000.0 + 300, None)
    assert dist_km(p, q) < 0.01


def test_side_adjective_not_village():
    """11.11: «Західним курсом…», «Північним курсом…», «Південні турби…» — напрям, а не села Західне/Північне/Південне."""
    from app.parser import Parser
    p = Parser()
    assert [q.place.name for q in p.parse("Західним курсом на Дніпропетровщину", "eyes_everywhere_ua").places] == []
    assert [q.place.name for q in p.parse("Північним курсом далі на Новогупалівку", "operatyvnohlep").places] == ["Новогупалівка"]
    names = [q.place.name for q in p.parse("Ⓜ️⚜️ Південні турби змінили курс, летять в сторону Солоне, далі на Дніпро.", "nikalert").places]
    assert "Південне" not in names and "Солоне" in names
    # справжні пункти лишаються
    assert [q.place.name for q in p.parse("2х Бандеролі на Південне", "odessa_inform").places] == ["Південне"]
