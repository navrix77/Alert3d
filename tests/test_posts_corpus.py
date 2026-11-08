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


def test_molniya_at_border_points_inland():
    """08.11: «Молнія курсом на Козачу Лопань» (за кілька км від кордону): носом на південь, вглиб, а не без курсу."""
    import time
    m, t = _tracker()
    now = time.time()
    m.feed(t, "Молнія на Козачу Лопань⚠️", "M", now - 120, None, log=False)
    m.feed(t, "🟧Молния курсом на Казачью Лопань", "CXID", now - 60, None, log=False)
    hd = t.snapshot(now)["tracks"][0]["hd"]
    assert hd is not None and 120 < hd < 250, hd


def test_fpv_route_never_backwards_or_beyond_range():
    """08.11: маршрут FPV не веде назад до кордону й не виходить за дальність від лінії пуску."""
    import time
    from app.tracker import Tracker, SHORT_RANGE
    m, t = _tracker()
    now = time.time()
    m.feed(t, "FPV на Велику Данилівку", "M", now - 240, None, log=False)
    m.feed(t, "FPV курсом на Руську Лозову", "M", now - 60, None, log=False)
    for tr in t.snapshot(now)["tracks"]:
        if tr["type"] in ("fpv", "fpvf"):
            d0 = Tracker._front_dist(__import__("app.geo", fromlist=["x"]).to_xy(tr["lat"], tr["lon"]))
            for la, lo in tr["route"]:
                dd = Tracker._front_dist(__import__("app.geo", fromlist=["x"]).to_xy(la, lo))
                assert dd >= d0 - 0.6 and dd <= SHORT_RANGE[tr["type"]] + 0.1


def test_short_range_zone_and_heading_away_from_front():
    """08.11: у «Молнії» є зона ризику (віяло), а курс ніколи не веде до лінії пуску."""
    import time
    from app.tracker import Tracker
    from app.geo import to_xy
    m, t = _tracker()
    now = time.time()
    m.feed(t, "Молнія на Козачу Лопань⚠️", "M", now - 120, None, log=False)
    tr = t.snapshot(now)["tracks"][0]
    assert tr["zone"] and len(tr["zone"]["poly"]) > 10
    fb = Tracker._front_bearing(to_xy(tr["lat"], tr["lon"]))
    if fb is not None:
        from app.tracker import ang_diff
        assert ang_diff(tr["hd"], fb) <= 90


def test_molniya_does_not_drift_far_from_last_named_place():
    """08.11: пости «Молнія на Прудянку → маневрує біля Козачої Лопані» — не ≥15 км від останнього пункту й не на північ."""
    import time
    from app.geo import to_xy
    from app.tracker import dist_km
    m, t = _tracker()
    now = time.time()
    for dt, k, x in [(-1700, "M", "Молнія на Козачу Лопань⚠️"), (-1100, "M", "Молнія на Прудянку⚠️"), (-700, "M", "Молнія маневрує біля Козачої Лопані⚠️")]:
        m.feed(t, x, k, now + dt, None, log=False)
    tr = t.snapshot(now)["tracks"][0]
    assert dist_km(to_xy(50.3368, 36.1904), to_xy(tr["lat"], tr["lon"])) <= 10
    assert 120 < tr["hd"] < 250


def test_fpv_closed_by_fall_replies():
    """08.11: «Упал» (відповідь каналу) і «Взрыв в районе Дафи» знімають FPV; Дафі/Ужвій/Северка/Студентська розпізнаються."""
    import time
    now = time.time()
    m, t = _tracker()
    m.feed(t, "FPV СС/БД⚠️", "TLK", now - 200, None, log=False)
    m.feed(t, "Упал😔", "TLK", now - 30, None, log=False)
    assert all(x["status"] == "closed" for x in t.snapshot(now)["tracks"])
    m, t = _tracker()
    m.feed(t, "FPV-дрон курсом на ТРЦ Дафі ‼️", "M", now - 200, None, log=False)
    m.feed(t, "Взрыв в районе Дафи", "KHN", now - 30, None, log=False)
    assert all(x["status"] == "closed" for x in t.snapshot(now)["tracks"])
    for txt, nm in [("FPV-дрон курсом вул. Наталії Ужвій", "Ужвій"), ("ФПВ над Северкой", "Салтівка"), ("FPV-дрон курсом на метро Студентська", "Студентська")]:
        o = P.parse(txt, "M")
        assert any(nm in r.place.name for r in o.places), (txt, o.places)


def test_boom_event_on_fall():
    """08.11: коли ціль знято «Упал»/«Взрыв», у снапшоті є fx з її координатами (клієнт малює вибух)."""
    import time
    now = time.time()
    m, t = _tracker()
    m.feed(t, "FPV-дрон курсом на ТРЦ Дафі ‼️", "M", now - 200, None, log=False)
    m.feed(t, "Взрыв в районе Дафи", "KHN", now - 30, None, log=False)
    fx = t.snapshot(now)["fx"]
    assert fx and fx[0]["type"] == "fpv" and 49.9 < fx[0]["lat"] < 50.2


@pytest.mark.parametrize("reply", ["Не наблюдается ⚠️", "Упал😔", "Збили", "Ціль знищена", "Ціль припинила існування", "Пропал", "Відпрацювало ППО"])
def test_target_removed_by_end_synonyms(reply):
    """08.11: «не наблюдается / впав / збили / знищено / пропала» — відповідь каналу на його ж пост знімає ціль."""
    import time
    now = time.time()
    m, t = _tracker()
    m.feed(t, "Ударный на Дергачи⚠️", "TLK", now - 120, None, log=False)
    assert any(x["status"] == "active" for x in t.snapshot(now)["tracks"])
    m.feed(t, reply, "TLK", now - 20, None, log=False)
    assert not any(x["status"] == "active" for x in t.snapshot(now)["tracks"]), reply


@pytest.mark.parametrize("text,ch,place", [
    ("Одеса: шахед на Молдаванку", "M", "Молдаванка"), ("Дніпро, ударний на Діївку", "M", "Діївка"), ("Суми: БпЛА на Ковпаківський район", "M", "Ковпаків"),
    ("ФПВ на Ліски, Миколаїв", "M", "Ліски"), ("Кривий Ріг, шахед на Інгулець", "M", "Інгулець"), ("Херсон: дрон на Корабельний", "M", "Корабельний"),
    ("Львів, шахед на Сихів", "M", "Сихів"), ("шахед на Салтівку", "M", "Салтівка"),
])
def test_city_districts(text, ch, place):
    """08.11: райони й орієнтири не лише Харкова: Дніпро, Одеса, Суми, Миколаїв, Херсон, Кривий Ріг, Львів…"""
    o = P.parse(text, ch)
    assert any(place in r.place.name for r in o.places), (text, o.places)


def test_airport_not_odesa_port():
    o = P.parse("аеропорт Бориспіль", "M")
    assert not any("Одеський порт" in r.place.name for r in o.places)


def test_tg_web_reply_preview_not_taken_as_text():
    """08.11: у t.me/s цитоване повідомлення стоїть першим (js-message_reply_text) — його текст не має підміняти справжній."""
    from app import tg_web
    page = ('<div class="tgme_widget_message_wrap"><div class="tgme_widget_message js-widget_message" data-post="TLK/1">'
            '<a class="tgme_widget_message_reply js-message_reply" href="x"><div class="tgme_widget_message_text js-message_reply_text">Далее МД⚠️</div></a>'
            '<div class="tgme_widget_message_text js-message_text" dir="auto">Не наблюдается ⚠️</div>'
            '<time datetime="2026-11-08T13:36:00+02:00"></time></div></div>')
    assert [x[2] for x in tg_web.parse_page(page)] == ["Далее МД⚠️ — Не наблюдается ⚠️"]  # 08.11: короткий коментар отримує контекст цитати


def test_reply_context_kab_fell():
    """08.11: «Впав 💥» у відповідь на «КАБ курсом на Старий Салтів» знімає цю зону (монітор 1654)."""
    from app.tg_web import parse_page
    from app.tracker import Tracker
    pg = ('<div class="tgme_widget_message x" data-post="M/5"><a class="tgme_widget_message_reply js-message_reply" href="x">'
          '<div class="tgme_widget_message_text js-message_reply_text">КАБ курсом на Старий Салтів⚠️</div></a>'
          '<div class="tgme_widget_message_text js-message_text">Впав 💥</div><time datetime="2026-11-08T14:38:00+02:00"></time></div>')
    txt = parse_page(pg)[0][2]
    assert "Старий Салтів" in txt
    import time
    import app.main as m
    from app import config
    trk = Tracker(config.SOURCES, m.brain)
    now = time.time()
    m.feed(trk, "КАБ курсом на Старий Салтів⚠️", "M", now - 120, None, log=False)
    assert trk.zones
    m.feed(trk, txt, "M", now - 60, None, log=False)
    assert not trk.zones


def test_saltivka_microdistrict_numbers():
    def _pl(t, src):
        return [(r.place.name, 0, 0) for seg in P.segments(t) for r in P.parse(seg, src).places]
    """08.11: «ФПВ на 533» — мікрорайон Салтівки; число без прийменника чи з «метрів/шт» — не місце."""
    assert [n for n, _a, _b in _pl("ФПВ со стороны Бобровки на 533", "KHN")][0].startswith("мкр Салтівка")
    assert [n for n, _a, _b in _pl("ФПВ на 602", "KHN")] == ["мкр Салтівка 600-х (Харків)"]
    assert not _pl("3 шахеди на 600 метрів", "KHN") and not _pl("на 5 шахедів", "KHN")


def test_credit_line_not_a_place():
    """08.11: «Відео/фото: Труха, СТО Харків» (Де у Харкові) — підпис, а не ціль FPV на Харків."""
    t = "Перші кадри з місця прильоту FPV по Київському району.\nБуло влучання двох ФПВ дронів по автівкам.\n\nВідео/фото: Труха, СТО Харків"
    for seg in P.segments(t):
        assert P.parse(seg, "place_kharkiv").kind == "filtered"
    assert "Харків" not in " ".join(P.segments(t))


def test_past_fpv_report_is_not_a_target():
    """08.11: «російські війська завдали ударів FPV-дронами по Київському району Харкова» (прокуратура) — звіт, не ціль."""
    o = P.parse("8 листопада російські війська завдали ударів FPV-дронами по Київському району Харкова.", "KM")
    assert o.kind != "track" and o.no_target
    assert P.parse("FPV курсом на Харків", "KM").kind == "track"
