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


def test_tts_stress_fix():
    import pytest
    pytest.importorskip("piper")
    pytest.importorskip("ukrainian_word_stress")
    from app import tts
    ph = "".join(p for s in tts.phonemize_text("Шахед летить, вісім хвилин") for p in s)
    assert "ʃaxˈɛd" in ph and "lɛt̪ˈɪt" in ph and "ɣβɪlˈɪn" in ph  # шахе́д, лети́ть, хвили́н — не ша́хед/ле́тить/хви́лин


def test_audit_2026_11_02_raions_hromadas(monkeypatch):
    """Аудит 02.11.2026: на ПК без shapely «Полтавський район» ставав селом Полтавське (Харківщина),
    список районів — селом Кременчуки (Хмельниччина), «Покровська ТГ» у каналі Нікопольщини — Покровськом на Донеччині."""
    import sys
    from app import parser as pm
    from app.parser import Parser
    monkeypatch.setitem(sys.modules, "shapely", None)
    monkeypatch.setitem(sys.modules, "shapely.geometry", None)
    monkeypatch.setattr(pm, "_RAIONS", None)
    p = Parser()
    names = lambda t, ch: [r.place.name for r in p.parse(t, ch).places]
    assert names("Полтавський район Щас буде тривога через реактивні з дніпра", "ppopoltavanightfighters") == ["Полтавський р-н"]  # 02:39
    assert sorted(names("Полтавський та Кременчуцький райони", "PL")) == ["Кременчуцький р-н", "Полтавський р-н"]  # 06:15
    assert sorted(names("Кременчуцький, Полтавський райони, тривога: загроза БпЛА", "ppo_poltava")) == ["Кременчуцький р-н", "Полтавський р-н"]  # 09:07
    o = p.parse("◼️ 02:48 Покровська ТГ", "nikalert")  # те саме о 05:11, 06:58, 07:19, 08:13 …
    assert [r.place.name for r in o.places] == ["Покровська ТГ"] and o.places[0].place.lon < 35


def test_audit_2026_11_02_words_not_villages():
    """Аудит 02.11.2026: звичайні слова й назви регіонів ставали селами через нечіткий пошук."""
    from app.parser import Parser
    p = Parser()
    names = lambda t, ch: [r.place.name for r in p.parse(t, ch).places]
    # Волині → Волфине, Буковини → Буковина (eRadarrua 08:29, tgsn_ua 08:35, truexanewsua 08:35)
    assert names("Найбільша загроза для Львівщини, Рівненщини, Івано-Франківщини, Волині, Тернопільщини та Буковини, включаючи їхні обласні центри.", "eRadarrua") == []
    assert names("▪️Найбільша загроза — для західних областей: Львівщини, Рівненщини, Івано-Франківщини, Волині, Тернопільщини та Буковини.", "tgsn_ua") == []
    # дронопорт під Орлом — не Цимбалове на Полтавщині (horizon_of_war_Official 09:18, RadarChernihiv 09:19)
    assert names("⚠️ За наявною інформацією, противник доставив до Орла (Цимбулово) близько 60 реактивних БпЛА типу «Герань-4/5».", "horizon_of_war_Official") == []
    assert names("За наявною інформацією, ворог здійснив доставку ~60 реактивних БпЛА на дронопорт «Цимбулова».", "RadarChernihiv") == []
    # Швидкісна → Шведчина, Попередній → Поперечне, Слідчі → Сліди, Прислати → Преслав
    assert names("Швидкісна на Одесу від Коси", "Shturval_media")[0] == "Одеса"
    assert "Поперечне" not in names("⚠️ Попередній на Вінниччині вже пройшов Ладижин, далі курсом на Гайсин.", "UkraineRadar_24_7")
    assert names("Слідчі Служби безпеки повідомили агенту про підозру", "temporis_odesa") == []
    assert names("📩 Прислати фото/відео", "operatyvnyi_donbas") == []
    # нечіткий пошук і далі знаходить відмінки й рос. написання
    assert names("Комишувасі, Балабиному, Юрківці, Жовтій Кручі, Терсянці,", "info_zp")[0] == "Комишуваха"
    from app.geo import Gazetteer
    g = Gazetteer.load()
    for w, n in [("Кременчуга", "Кременчук"), ("Одессы", "Одеса"), ("Мерефы", "Мерефа"), ("Северодонецка", "Сіверськодонецьк")]:
        assert g.places[g.lookup(w)[0]].name == n, w


def test_audit_2026_11_02_sumline_zaporizhzhia():
    """kiev_nebo 08:22: «1 на Запоріжжі – Комишуваха (1)» — Запоріжжі тут область, а не село Запоріжжя на Чернігівщині."""
    from app.parser import Parser
    p = Parser()
    for t, n in [("1 на Запоріжжі – Новомиколаївка (1).", "Новомиколаївка"), ("1 на Запоріжжі – Комишуваха (1).", "Комишуваха")]:
        segs = p.segments(t)
        assert len(segs) == 1
        o = p.parse(segs[0], "kiev_nebo")
        assert [r.place.name for r in o.places] == [n] and o.oblast_hint == "Запорізька"
        assert 46.6 < o.places[0].place.lat < 48.3 and 34.2 < o.places[0].place.lon < 37.3


def test_journal_2026_11_02_words_and_headers():
    """Журнал повідомлень 01–02.11.2026: підписи, рубрики й аеродроми рф не стають селами."""
    from app.parser import Parser
    p = Parser()
    names = lambda t, ch: [r.place.name for r in p.parse(t, ch).places]
    # «– Повітряні Сили» ≠ село Сила (khmlv 20:18, 05:42)
    assert names("🛸 БпЛА з півночі Хмельниччини на Рівненщину, – Повітряні Сили", "khmlv") == []
    assert names("🛸 Реактивний БпЛА на півночі Вінниччини, курс на Хмельниччину, – Повітряні Сили", "khmlv") == []
    # «Вектор» ≠ Вікторія (MK 12:29, SU 14:05)
    assert names("1 БпЛА перелітає з Хмельниччини на Буковину. Вектор на Чернівці.", "MK") == ["Чернівці"]
    assert "Вікторія" not in names("Вектор КАБів Храпівщина-Кияниця", "SU")
    # «Кр.Ріг:» — рубрика nikalert (21:55, 02:38), а не село Ріг
    assert names("Ⓜ️📡 Кр.Ріг: 1 Нива Трудова", "nikalert") == ["Нива Трудова"]
    assert names("Ⓜ️⚒️ Кр.Ріг : Це звичайний БпЛА біля Покрова", "nikalert") == ["Покров"]
    # рос. двослівна назва (D 21:57, CX 21:56, R 21:21)
    assert names("⚠️на Питомник, Черкасскую Лозовую, Харьков", "D")[:2] == ["Питомник", "Черкаська Лозова"]
    assert names("🔴 Ударный в направлении Черкасской Лозовой", "CX") == ["Черкаська Лозова"]
    assert "Черкаська Лозова" in names("Ударный на Питомник / Черкасская Лозовая ⚠️", "R")
    # аеродроми рф (MU, UkraineRadar_24_7, krolevetsnews): не Українка на Київщині, не Олине
    assert names("✈️Зліт двох бортів Ту-95мс з аер.Українка, ймовірно переліт на аер.Оленья.", "UkraineRadar_24_7") == []
    assert names("Передислокація щонайменше   2 Ту-95мс з ае. «Українка» на ае. «Оленья».", "krolevetsnews") == []
    assert names("1 реактивний курсом на Андріївка/Донець", "Karkivw")[0] == "Андріївка"  # «а/Д» — не аеродром
    # «Більше …» ≠ Білаші (PL, ppopoltavanightfighters)
    assert names("Більше 5 нових шахедів вздовж межі Харківщини та Дніпропетровщини курсом в район Нехворощі.", "PL") == ["Нехвороща"]
    assert names("Більше скажу нових до нас не фіксується", "ppopoltavanightfighters") == []
    # відмінки, які жорсткіший нечіткий пошук не має губити
    assert names("Ударний БПЛА маневрує біля Дергачів⚠️❗️", "M") == ["Дергачі"]
    assert names("🔴Шахед на Центр Чернівців!", "MU") == ["Чернівці"]
    assert names("2 шахеда між Полтавою та Новими Санжарами курсом на Решетилівку.", "PL") == ["Нові Санжари", "Решетилівка"]


def test_journal_2026_11_02_sumline_notes_and_cities():
    from app.parser import Parser
    p = Parser()
    # kiev_nebo 02:37: пояснення після кількості — зведення не губиться
    segs = p.segments("2 на Київщині – Київ (1, повз Козин), Пісківка (1, з Житомирщини)")
    assert [[r.place.name for r in p.parse(s, "kiev_nebo").places] for s in segs] == [["Київ"], ["Пісківка"]]
    segs = p.segments("1 на Миколаївщині – Очаків (1, з акваторії Чорного моря)")
    assert [[r.place.name for r in p.parse(s, "kiev_nebo").places] for s in segs] == [["Очаків"]]
    # місто за межами регіону каналу, а не село-тезка біля його кордону
    for t, ch, lat in [("🔻 Один БпЛА повз Гощу на Рівне", "kiev_nebo", 50.6), ("БпЛА на Запоріжжя.", "kiev_nebo", 47.85),
                       ("БпЛА курсом на Запоріжжя", "D", 47.85)]:
        pl = [r.place for r in p.parse(t, ch).places]
        assert pl and pl[-1].kind == "M" and abs(pl[-1].lat - lat) < 0.2, (t, pl)


def test_journal_2026_11_02_no_jet_teleport():
    """РБ-27, 02.11 03:35–03:36: «курсом на X» від кількох каналів щохвилини переносило ціль у X —
    Васильків → Петропавлівська Борщагівка 26 км за ~40 с (2195 км/год). Тепер X лишається курсом."""
    from app.parser import Parser
    from app.geo import dist_km
    p = Parser()
    tr = Tracker(SOURCES)
    t0 = 1_793_583_299  # 03:34:59 Київ
    msgs = [(0, "KL", "Реактивний БпЛА курсом на Боярку (Київщина)"),
            (35, "truexakyiv", "Реактивний на Васильків."),
            (62, "UkraineRadar_24_7", "‼️ 1х реактивний на Київщині курсом на Васильків!  Далі може піти в бік Глевахи."),
            (96, "KL", "Реактивний БпЛА курсом на Петропавлівську Борщагівку (Київщина)"),
            (105, "rozvidkaneba", "Реактивний БпЛА курсом на Петропавлівську Борщагівку (Київщина)")]
    for dt, src, text in msgs:
        for s in p.segments(text):
            tr.ingest(p.parse(s, src), src, t0 + dt)
    for track in tr.tracks:
        for a, b in zip(track.obs, track.obs[1:]):
            d = dist_km((a.x, a.y), (b.x, b.y))
            v = d / max(30.0, b.t - a.t) * 3600
            assert not (d > 25 and v > 450 * 3), (track.id, a.label, b.label, round(d), round(v))
def test_lozova_vs_lozove():
    from app.parser import Parser
    p = Parser()
    # R/TLK: «на Лозовую» — місто Лозова (Лозове було б «Лозовое»)
    for t, ch in [("Два Реактивных Шахеда на Лозовую⚠️🛸", "R"), ("Ещё 2 Р. Шаболды на Лозовую⚠️", "TLK"), ("Шахед на Лозову", "M")]:
        assert [r.place.name for r in p.parse(t, ch).places] == ["Лозова"]
    assert [r.place.name for r in p.parse("Шахед на Лозове").places] == ["Лозове"]
    assert [r.place.name for r in p.parse("Шахеды на Белую Церковь").places] == ["Біла Церква"]
