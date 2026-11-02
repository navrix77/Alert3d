"""Тести парсера й трекера. Реплей — структуровані спостереження реальної ночі 29→30.10.2026."""
import json
from pathlib import Path

from app.config import SOURCES
from app.geo import Place
from app.parser import Observation, Parser, PlaceRef
from app.tracker import Tracker

P = Parser()


def names(obs, role=None):
    return [r.place.name for r in obs.places if role is None or r.role == role]


def test_jet_list_ru():
    o = P.parse("❗ Реактивный шахед курсом на Чугуев, Змиев, Мерефу")
    assert o.type == "jet" and o.kind == "track"
    assert names(o)[:3] == ["Чугуїв", "Зміїв", "Мерефа"]


def test_shahed_position_uk():
    o = P.parse("2х БпЛА в районі Богодухова, курсом на Харків")
    assert o.type == "shahed" and o.count == 2
    assert names(o, "p") == ["Богодухів"] and "Харків" in names(o, "t")


def test_kab_zone_with_oblast_hint():
    o = P.parse("❗❗ БОМБЫ курсом на Боровую, Изюм Харьковской области")
    assert o.kind == "zone" and o.type == "kab"
    assert {"Борова", "Ізюм"} <= set(names(o))


def test_safety_filter():
    assert P.parse("Чути роботу ППО в районі Харкова").kind == "filtered"
    assert P.parse("Взрыв в районе Андреевки").kind == "filtered"


def test_close():
    assert P.parse("БпЛА по Харкову більше не фіксуються").kind == "close"


TYMAP = {"S": "shahed", "J": "jet", "M": "molniya", "C": "cruise", "B": "ballistic", "K": "kab"}


def test_replay_real_night():
    d = json.loads((Path(__file__).parent / "night_2026-10-29.json").read_text(encoding="utf-8"))
    places = [Place(n, la, lo, "C") for n, la, lo in d["places"]]
    tr = Tracker(SOURCES)
    t0 = 1_761_764_400  # 29.10.2026 21:00 Київ
    for t, s, mid, ty, cnt, fl, pl in d["recs"]:
        refs = [PlaceRef(r, places[v]) for r, v in pl if places[v].name != "Харківщина"]
        o = Observation(type=TYMAP.get(ty), count=cnt or None, places=refs, close="x" in fl, safety="p" in fl, aviation="a" in fl)
        tr.ingest(o, s, t0 + t * 60)
    snap = tr.snapshot(t0 + 452 * 60)
    act = [x for x in snap["tracks"] if x["status"] == "active"]
    assert len(tr.tracks) > 20 and act, "мають бути активні треки"
    assert "Харківська" in snap["levels_tracker"]


def test_alerts_mixed_levels():
    from app.alerts import OfficialAlerts
    rest = ("— air raid alert. 3 areas affected: red (missile / mass-strike level): Chuhuivskyi (Чугуївський), m. Kharkiv (м. Харків); "
            "yellow (drone level): Kupyanskyi (Куп'янський). The most recent to go under alert was m. Kharkiv (м. Харків) at 19:07.")
    assert OfficialAlerts.parse_areas(rest) == [("Чугуївський", 2), ("м. Харків", 2), ("Куп'янський", 1)]
    old = "3 areas affected: Myrhorodskyi (Миргородський), Lubenskyi (Лубенський) [yellow (drone level)]."
    assert OfficialAlerts.parse_areas(old) == [("Миргородський", 1), ("Лубенський", 1)]


def test_launch_detect():
    from app.launch import detect
    assert [s.name for s in detect("Пуски шахедів з Приморсько-Ахтарська", "shahed")[0]] == ["Приморсько-Ахтарськ"]
    assert detect("Зліт Ту-95МС з аеродрому Енгельс", None)[2] == "Ту-95МС/Ту-160"
    assert detect("Вибухи в Бєлгороді", None)[0] == []
    assert detect("З Орелі на Новомосковськ", None)[0] == []
    assert detect("В ніч на 1 листопада атакував 98 БпЛА з напрямків: Курськ, Орел", "shahed")[3]
    assert detect('Найближчим часом очікується передислокація Ту-95МС з аеродрому "Українка" на аеродром "Оленья".', "kab")[0] == []
    assert detect("Зліт Ту-95МС з Оленья, носії бомб", "kab")[1] == "cruise"


def test_push_threat():
    from app.geo import to_xy
    from app.push import Push
    H = to_xy(50.00, 36.23)  # Харків
    tr = {"lat": 50.30, "lon": 36.23, "speed": 170, "hd": 180.0, "route": [[36.23, 49.90]], "type": "shahed", "count": 1}
    r = Push.threat(tr, H)
    assert r and r[2] == "півночі" and 9 < r[1] < 13
    tr2 = dict(tr, hd=0.0, route=[])
    assert Push.threat(tr2, H) is None


def test_parser_real_world_cases():
    from app.parser import Parser
    P = Parser()
    pl = lambda t, c=None: [(r.role, r.place.name) for r in P.parse(t, c).places]
    assert P.parse("🟡 Сумський район — повітряна тривога, жовтий рівень: Дронова загроза", "SU").kind == "info"
    assert pl("Великий Вистороп > Михайлівка шах", "SU") == [("p", "Великий Вистороп"), ("t", "Михайлівка")]
    assert pl("Чугуїв: шахед курсом на Харків", "M") == [("p", "Чугуїв"), ("t", "Харків")]
    assert pl("Ракетний удар по Харкову", "M")[0][1] == "Харків"
    assert pl("БпЛА на Лозову")[0][1] == "Лозова" and P.parse("БпЛА на Лозову").places[0].place.lat < 49.2
    assert P.parse("Ударний на Безлюдівку", "M").type == "shahed"
    assert pl("Шахед над Трухановим островом", "kievreal1") == [("p", "Труханів острів (Київ)")]
    assert [r.place.name for r in P.parse("Ударний на Холодну Гору", "M").places] == ["Холодна Гора (Харків)"]


def test_alerts_single_area_not_whole_oblast():
    from app.alerts import OfficialAlerts
    o = OfficialAlerts()
    o.apply_md("## 3. X\n**Kharkivska oblast (Харківська область)** — air raid alert in effect since 20:20. 1 area affected: Iziumskyi (Ізюмський) [red (missile / mass-strike level)].\n## 4. Y")
    assert o.oblast_levels == {} and o.raion_levels == {"Ізюмський": 2}


def test_tlk_slang():
    from app.parser import Parser
    P = Parser()
    assert P.parse("Р. Шаболда на Изюм⚠️", "TLK").type == "jet"
    assert P.parse("Ударный на Дергачи⚠️", "TLK").type == "shahed"
    assert P.parse("По ударным", "TLK").kind == "close"
    assert P.parse("Развед. БПЛА над Изюмом⚠️", "TLK").kind == "info"
    assert [r.place.name for r in P.parse("Далее ЛГ/Залютино/ХГ⚠️", "TLK").places][0] == "Лиса Гора (Харків)"


def test_missile_removed_after_explosion_and_silence():
    from app.parser import Parser
    from app.tracker import Tracker
    p, tr = Parser(), Tracker(SOURCES)
    t0 = 1_800_000_000
    o = p.parse("Ракета курсом на Харків", "ND")
    tr.ingest(o, "ND", t0)
    act = [x for x in tr.snapshot(t0 + 30)["tracks"] if x["status"] == "active" and x["type"] == "cruise"]
    assert act
    # вибухи в Харкові — ракету прибрано (саме повідомлення не публікується)
    tr.ingest(p.parse("Вибухи в Харкові", "ND"), "ND", t0 + 60)
    assert not [x for x in tr.snapshot(t0 + 70)["tracks"] if x["status"] == "active" and x["type"] == "cruise"]
    # інша ракета, про яку мовчать, зникає за кілька хвилин
    tr.ingest(p.parse("Ракета курсом на Полтаву", "ND"), "ND", t0 + 100)
    assert not [x for x in tr.snapshot(t0 + 100 + 420)["tracks"] if x["status"] == "active" and x["type"] == "cruise"]


def test_continuation_word_is_not_a_place():
    from app.parser import Parser
    o = Parser().parse("🟧 Дальше курс на Печенеги/Чугуев  ✅ Підпишись на СХІД", None)
    names = [r.place.name for r in o.places]
    assert "Дальнє" not in names and not any(r.role == "p" for r in o.places)
    assert names[:2] == ["Печеніги", "Чугуїв"]


def test_regional_channel_stays_in_region():
    from app.parser import Parser
    p = Parser()
    o = p.parse("БпЛА з півдня на Піски", "operatyvnohlep")  # Запоріжжя: Піски — район міста, не село на Харківщині
    assert o.places and all(46 < r.place.lat < 48.3 for r in o.places)
    o = p.parse("⚠️ Пуски шахедів з Південного напрямку", "monikppy")
    assert not any(r.place.name == "Південне" for r in o.places)


def test_new_adjective_is_not_village_nove():
    from app.parser import Parser
    o = Parser().parse("🛵Новий реактивний БпЛА з т.о.Криму в бік Одещини", None)
    assert not any(r.place.name == "Нове" for r in o.places)


def test_alert_lines_and_fpv_are_not_targets():
    from app.parser import Parser
    p = Parser()
    for ch, t in [("UkraineAlarmSignal", "🛸 Ворожба (Сумська обл.)"), ("UkraineAlarmSignal", "◻️ 00:10 Нікополь"),
                  ("kherson_non_drone", "[🗺] У районі селища Білозерка — активність дрона типу «FPV», повідомляють очевидці")]:
        o = p.parse(t, ch)
        assert o.kind != "track" and o.no_target, t
    assert p.parse("🔴 Шахед на Полтаву", None).kind == "track"
    assert p.parse("💥 Харків", None).kind == "filtered"


def test_explicit_new_types():
    from app.parser import Parser
    p = Parser()
    assert p.parse("Бандероль курсом на Харків").type == "banderol"
    assert p.parse("Герань-5 на Полтаву").type == "geran5"
    assert p.parse("FPV у районі Білозерки").type == "fpv"
    assert p.parse("FPV на оптоволокні біля Херсона").type == "fpvf"
    assert p.parse("Шахед на Полтаву").type == "shahed"
    assert p.parse("Град пройшов у Києві").type != "rszv"


def test_kab_zone_lifecycle():
    import time
    from app import config
    from app.parser import Parser
    from app.tracker import Tracker
    p, tr = Parser(), Tracker(config.SOURCES, learn=False)
    t = time.time() - 3600
    tr.ingest(p.parse("Активність тактичної авіації на північно-східному напрямку"), "x", t)
    tr.ingest(p.parse("КАБ на Золочів"), "x", t + 60)
    tr.ingest(p.parse("КАБ на Золочів"), "x", t + 120)
    tr.zones[0].last = time.time() - 60
    s = tr.snapshot()
    assert len(s["zones"]) == 1 and s["zones"][0]["n"] == 2  # повторна згадка не дублює зону
    tr.ingest(p.parse("Відбій загрози КАБ на Харківщині"), "x", time.time())
    assert not tr.snapshot()["zones"]
    tr.ingest(p.parse("КАБ на Золочів"), "x", time.time() - 11 * 60)  # 11 хв тиші, авіації вже нема
    assert not tr.snapshot()["zones"]


def test_review_regressions():
    import time
    from app import config
    from app.parser import Parser
    from app.tracker import Tracker
    p = Parser()
    # назви цілей — не села Шахи / Гербине
    o = p.parse("Шахеди на Полтаву", "K")
    assert [r.place.name for r in o.places] == ["Полтава"]
    assert p.parse("Герань 5 штук курсом на Полтаву").type == "shahed"
    assert p.parse("Герань-5 на Полтаву").type == "geran5"
    # Ту-22 / МіГ-31К — не зона КАБ
    assert p.parse("МіГ-31К злетів. Загроза для Києва").kind != "zone"
    # нові типи не валять snapshot (launch.link)
    tr = Tracker(config.SOURCES, learn=False)
    t = time.time()
    for s in ["Герань-5 на Охтирку", "Бандероль на Харків", "РСЗВ по Нікополю", "FPV у районі Білозерки"]:
        tr.ingest(p.parse(s), "x", t)
    tr.snapshot()
    # дві цілі від одного каналу в одному пункті не зливаються
    tr2 = Tracker(config.SOURCES, learn=False)
    tr2.ingest(p.parse("Шахед у районі Чугуєва"), "k", t)
    tr2.exclude = {tr2.tracks[0].id}
    tr2.ingest(p.parse("Шахед у районі Чугуєва"), "k", t + 5)
    tr2.exclude = set()
    assert len([x for x in tr2.snapshot()["tracks"] if x["status"] == "active"]) == 2


def test_night_audit_fixes():
    from app.parser import Parser
    p = Parser()
    # «Сумського району» — район, а не село Сумське за 500 км
    assert not any(r.place.name == "Сумське" for r in p.parse("Обстріл Сумського району реактивними системами залпового вогню", "rozvidkaneba").places)
    # «Петропавлівська Борщагівка» — село, а не київський мікрорайон
    o = p.parse("Реактивний БпЛА курсом на Петропавлівську Борщагівку (Київщина)", "rozvidkaneba")
    assert [r.place.name for r in o.places] == ["Петропавлівська Борщагівка"]


def test_learned_prediction_not_course():
    import time
    from app import config
    from app.parser import Parser
    from app.tracker import Tracker

    class B:  # мозок, що «навчився» хибного кроку за 200 км
        def next_places(self, *a, **k):
            return [("Циркуни", 0.9, 50.08, 36.39)]

        def next_path(self, *a, **k):
            return []

        def rel(self, s, prior):
            return prior

        def __getattr__(self, n):
            return lambda *a, **k: None
    p = Parser()
    assert [r.place.name for r in p.parse("🟧 Р. Шахед курсом на Лозовую/Днепропетровскую область", "CX").places] == ["Лозова"]
    tr = Tracker(config.SOURCES, B(), learn=False)
    tr.ingest(p.parse("Шахед у районі Лозової"), "x", time.time())
    t = [x for x in tr.snapshot()["tracks"] if x["status"] == "active"][0]
    assert t["next"] is None and t["route_names"] == []  # навчене — не курс


def test_summary_lines_are_positions():
    from app.parser import Parser
    p = Parser()
    segs = p.segments("Шахеди:\n3 на Дніпропетровщині – Тернівка (1), Шахтарське (1), Петропавлівка (1).")
    obs = [p.parse(s, "kiev_nebo") for s in segs]
    pos = [(r.role, r.place.name) for o in obs for r in o.places]
    assert ("p", "Тернівка") in pos and all(r == "p" for r, _ in pos)  # місця зараз, а не «курс → Петропавлівка»


def test_night_0630_fixes():
    from app.parser import Parser
    p = Parser()
    # monikppy: перелік пунктів — це поточні місця, не «курс → Ізмаїл» на 540 км
    segs = p.segments("Чорнобай, Білики, Юріївка, Очаків, Вилкове, Кілія, Ізмаїл.")
    assert len(segs) == 7 and all(r.role == "p" for s in segs for r in p.parse(s, "monikppy").places)
    # Angry_Pol: «Житомирської та Київської областей» — не село Житомирське в Криму
    o = p.parse("БпЛА по межі Житомирської та Київської областей в напрямку Погребище ( Вінниччина)", "Angry_Pol")
    assert [r.place.name for r in o.places] == ["Погребище"]


def test_zircon_not_tsyrkuny_and_expectations_not_targets():
    from app.parser import Parser
    p = Parser()
    o = p.parse("◾️ Також у рамках нанесення комбінованого удару, очікується застосування балістичних ракет «Іскандер-М» та ракет РМ-48У, ракет «Циркон», корейських «KN-23»", "truexanewsua")
    assert o.kind != "track" and not any(r.place.name == "Циркуни" for r in o.places)
    assert p.parse("Циркон курсом на Київ").type == "ballistic"
    assert [r.place.name for r in p.parse("Шахед на Циркуни").places] == ["Циркуни"]


def test_kab_aftermath_and_raions():
    from app.parser import Parser
    p = Parser()
    # kharkivlife: підсумок наслідків — не зона КАБ
    assert p.parse("На фото сел. Васищеве, м. Ізюм та м. Лозова", "kharkivlife").kind != "zone"
    assert p.parse("▪️у Чугуївському районі пошкоджено складську будівлю (м. Чугуїв), трактор (сел. Пролісне).", "kharkivlife").kind != "zone"
    # CX: «Повторные пуски Каб на Изюмский район» → центр Ізюмського району
    o = p.parse("Повторные пуски Каб на Изюмский район", "CX")
    assert o.kind == "zone" and [r.place.name for r in o.places] == ["Ізюмський р-н"]
    assert [r.place.name for r in p.parse("Пуски Каб Изюм /район⚠️", "R").places] == ["Ізюм"]
