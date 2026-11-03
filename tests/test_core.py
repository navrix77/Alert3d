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
    assert P.parse("Развед. БПЛА над Изюмом⚠️", "TLK").type == "recon"  # розвідники — окремий тип (на прохання користувача)
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
    assert names("2 шахеда між Полтавою та Новими Санжарами курсом на Решетилівку.", "PL") == ["Полтава", "Нові Санжари", "Решетилівка"]  # орудний «Полтавою» тепер розпізнається


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


def test_city_over_village_namesake_in_region():
    from app.parser import Parser
    p = Parser()
    # TLK/CX (Харківщина) з контекстом біля Куп'янська: «на Лозовую» — місто Лозова, не село Лозова (50.18, 37.29)
    o = p.parse("2 Р. Шаболды на Лозовую⚠️", "TLK", (49.9, 37.5))
    assert o.places and abs(o.places[0].place.lat - 48.89) < 0.05


def test_struck_closes_target():
    import time
    from app import config
    from app.parser import Parser
    from app.tracker import Tracker
    p, tr = Parser(), Tracker(config.SOURCES, learn=False)
    t = time.time() - 300
    tr.ingest(p.parse("Шахед у районі Чугуєва"), "x", t)
    # Синєгубов: «Армія рф вдарила БПЛА по Чугуєву» — ціль уже вдарила, а не «змінила курс»
    o = p.parse("🔻 Армія рф вдарила БПЛА по Чугуєву.")
    assert o.kind == "filtered"
    tr.ingest(o, "OVA", t + 100)
    assert all(x["status"] != "active" for x in tr.snapshot()["tracks"])
    assert p.parse("Ударний БпЛА на Чугуїв").kind == "track"


def test_geran34_is_jet():
    from app.parser import Parser
    p = Parser()
    assert p.parse("🛸 Ще потенційні 2× рБпЛА «Герань-4» у напрямку Вінниці", "vinnradar").type == "jet"
    assert p.parse("Герань на Київ").type == "shahed"


def test_security_news_not_target():
    from app.parser import Parser
    p = Parser()
    o = p.parse("Військова контррозвідка Служби безпеки затримала в Одесі ще одного російського агента. Ним виявився колишній моряк торговельного судна, який коригував обстріли портового міста.", "temporis_odesa")
    assert o.kind != "track" and o.no_target




def test_analyst_sources_copies_and_nights():
    """Аналітик: перепост (той самий текст іншого каналу за 5 хв) — не незалежне джерело; «хто перший» — у межах 15 хв;
    ночі з іншим охопленням каналів не порівнюються."""
    from app.analyst import journal_groups, night_compare, source_stats, summary, corridors, plural
    t0 = 1_793_580_000
    rows = []
    for k in range(25):
        b = t0 + k * 4000
        rows += [(b, "KL", f"РБ-{k}", "jet", f"Реактивний БпЛА курсом на Боярку {k}"),
                 (b + 4, "rozvidkaneba", f"РБ-{k}", "jet", f"Реактивний БпЛА курсом на Боярку {k}"),   # копія
                 (b + 120, "K", f"РБ-{k}", "jet", f"🏍 Реактивний на Київщині {k}"),
                 (b + 3000, "late", f"РБ-{k}", "jet", f"інший текст {k}")]                           # пізно — не «відставання»
    st = {s["src"]: s for s in source_stats(journal_groups(rows))}
    assert st["KL"]["first_share"] == 1.0 and st["K"]["lag_med_s"] == 120
    assert st["rozvidkaneba"]["copy_share"] == 1.0 and "late" not in st
    n = night_compare(journal_groups(rows), t0 + 25 * 4000)
    assert n["comparable"] == 0 or n["avg_same_time"] is not None
    assert plural(1, ("ціль", "цілі", "цілей")) == "ціль" and plural(12, ("ціль", "цілі", "цілей")) == "цілей" and plural(23, ("ціль", "цілі", "цілей")) == "цілі"
    act = [{"id": "Ш-1", "type": "shahed", "lat": 49.6, "lon": 34.5, "hd": 270, "count": 3, "next": "Решетилівка"},
           {"id": "Ш-2", "type": "shahed", "lat": 49.5, "lon": 34.6, "hd": 280, "count": 2, "next": "Решетилівка"}]
    c = corridors(act)
    assert c[0]["n"] == 5 and c[0]["dir"] == "захід" and c[0]["next"] == ["Решетилівка"]
    r = {"active_n": 5, "active": {"shahed": 5}, "wave": {"new30": 5, "prev30": 1, "trend": "наростає", "peak12h": 5},
         "corridors": c, "targets": [], "oblast_p60": [], "launches": [], "nights": None, "sources": [], "self": {}}
    txt = " ".join(summary(r))
    assert "5 шахедів" in txt and "наростає" in txt and "Полтавщині, курс на захід" in txt


def test_pred_score_v2():
    """Самоперевірка прогнозу v2: влучання — ціль названо ≤15 км від X; промах — двічі названо деінде."""
    from app.brain import Brain
    from app.geo import Place
    from app.tracker import Point, Track
    from pathlib import Path as P_
    b = Brain(P_(":memory:"))
    tr_ = Tracker(SOURCES, b)
    t = Track("Ш-1", "shahed", 170)
    t.obs = [Point(0, 0, 0, "x", "A", None)]
    t.last_pred = ("X", (30.0, 0.0), 0, (0.0, 0.0), (0.0, 30.0))
    tr_._score_pred(t, (28.0, 2.0), 600)
    assert b.pacc["shahed@2"] == [1.0, 1.0] and t.last_pred is None
    t.last_pred = ("X", (30.0, 0.0), 1000, (0.0, 0.0), None)
    tr_._score_pred(t, (0.0, -20.0), 1300)
    t.obs.append(Point(1300, 0.0, -20.0, "x", "B", None))
    tr_._score_pred(t, (0.0, -40.0), 1600)
    assert b.pacc["shahed@2"] == [1.0, 2.0]


def test_journal_2026_11_02_sections_and_selfcheck_findings():
    """Знахідки scripts/selfcheck.py на журналі 01–02.11."""
    from app.parser import Parser
    p = Parser()
    names = lambda t, ch: [r.place.name for r in p.parse(t, ch).places]
    # UkraineRadar_24_7: кожен «⚠️ …» пункт зведення — окремий сегмент зі своєю областю
    t = ("⚠️ З Черкащини на Київщину 1х реактивний курсом на Переяслав.  ⚠️ 1х реактивний з Брянщини заходить на Чернігівщину, курсом на Городню.  "
         "⚠️ На Миколаївщині ще 1х реактивний курсом на Березанку.  ⚠️ На Одещині реактивний курсом на Подільськ.")
    segs = p.segments(t)
    got = [[(r.place.name, round(r.place.lat, 1)) for r in p.parse(s, "UkraineRadar_24_7").places] for s in segs]
    assert [g[0][0] for g in got] == ["Переяслав", "Городня", "Березанка", "Подільськ"]
    assert got[1][0][1] > 51.5 and got[2][0][1] < 47.5  # Городня на Чернігівщині, Березанка на Миколаївщині
    # область попереднього пункту діє на наступний
    segs = p.segments("⚠️ На Дніпропетровщині реактивний курсом на Синельникове.  ⚠️ 4х БпЛА курсом на Покровське, ще 1х на Тернівку.")
    pk = [r.place for r in p.parse(segs[1], "UkraineRadar_24_7").places if r.place.name == "Покровське"][0]
    assert pk.lat < 48.5
    # «Новий 1× уБпЛА», «Нові КАБи», «Нова версія»; але «Нова Слобода КАБ» — село
    assert names("🛸 Новий 1× уБпЛА «Герань-2» / «Гербера» у напрямку м. Погребище з Київщини.", "vinnradar") == ["Погребище"]
    assert "Нова" not in names("Нові КАБи на Межову/Слов'янку/Донеччину.", "shovnebi")
    assert names("Нова Слобода КАБ", "rdsprostir") == ["Нова Слобода"]
    assert names("Буду вам дуже дуже вдячний 🙏🏻❤️", "MU") == []
    # тезка за сотні км від названої в тексті області — відкидаємо
    assert names("БпЛА курсом на Глушкове (Полтавщина)", "KL") == []
    assert names("БпЛА від Липовця бере курс на Вороновицю (Вінниччина)", "KL") == ["Вороновиця"]  # не Липовиця на Прикарпатті
    # «Київський район» — район Одеси, а не Київщина; родовий множини «від Ромнів»
    assert names("❗️1х реактивний на Одесу. Київський р-н", "odessa_infonews") == ["Одеса"]
    assert names("1 від Ромнів курсом на Чернігівську область.", "sumyregion") == ["Ромни"]
    assert names("БпЛА курсом на Васильків", "KL") == ["Васильків"] and names("1 БпЛА на Бердичів/передмістя.", "MK") == ["Бердичів"]
    # «від Кривого Рогу»: раніше IndexError (повідомлення губилось), тепер Кривий Ріг
    assert [r.place.name for r in p.parse("Дрон на півдні від Кривого Рогу курсом на Дніпро", "DN").places][0] == "Кривий Ріг (пд)"
    assert names("Шахед на Кривой Рог", "DN") == ["Кривий Ріг"]


def test_daleko_not_village_and_avia_short_life():
    import time
    from app import config
    from app.parser import Parser
    from app.tracker import Tracker
    p = Parser()
    # shovnebi: «Далеко не полетять» — коментар, а не село Далеке
    assert not p.parse("Далеко не полетять", "shovnebi").places
    tr = Tracker(config.SOURCES, learn=False)
    tr.ingest(p.parse("Активність тактичної авіації на північно-східному напрямку"), "x", time.time() - 13 * 60)
    assert not tr.snapshot()["avia"]  # літак не «висить» на рубежі пусків пів години


def test_likely_recon():
    from app.parser import Parser
    p = Parser()
    o = p.parse("Над Сумами кружляє безпілотник", "x")
    assert o.type == "recon" and o.likely
    assert p.parse("Ударний БпЛА кружляє над Харковом", "x").type == "shahed"
    assert [r.place.name for r in p.parse("Висить БпЛА над Шосткою", "x").places] == ["Шостка"]


def test_strategic_aviation_moves_are_not_launches():
    """02.11 12:24–12:27: переліт/посадка Ту-95МС на «Оленья»/«Енгельс» і припущення «можливо пуски» ставали сповіщеннями «Пуск»."""
    from app import launch
    no = ["станом на зараз вже 3 Ту-95МС сіли на ае «Оленья». за наявною інформацією, борти споряджені ракетами Х-101.",  # PhantomChe
          "✈️— 4 борти здійснили посадку на аеродромі «Оленья»",                                                          # rozvidkaneba
          "✈️— 2 борти перебувають на аеродромі «Енгельс-2», ймовірно, для спорядження крилатими ракетами Х-101",
          "+3 борти переліт на ае Оленья",                                                                                # radar_ukr
          "Ще 1х Ту-95мс летить на Енгельс для спорядження крилатими ракетами.",                                          # tryvoga_chomu
          "⚡️Зафіксовано зліт Ту-95МС з аеродрому «Українка» — літаки почали вилітати приблизно пів години тому",          # ppo_poltava
          "Можливо пуски бандеролєй з Азовського моря 🤕",                                                                  # admiralbukhta
          "🏍 Реактивний БпЛА повз Українку в напрямку Києва.", "Реактив від Українки, 4800"]                              # Українка на Київщині
    for t in no:
        assert launch.detect(t, None)[0] == [], t
    sites, typ, carrier, _ = launch.detect("Пуски бандероль з району Азовського моря.", None)  # monikppy 12:28 — факт
    assert [s.name for s in sites] == ["Азовське море"] and typ == "banderol"
    bk = launch.LaunchBook()
    L = bk.add(sites, typ, None, carrier, "monikppy", None, 1_793_615_280, False, "Пуски бандероль з району Азовського моря.")
    assert L and L[0].carrier is None  # не «кораблі (Калібр)»
    assert [s.name for s in launch.detect("Зафіксовано пуск крилатих ракет з Ту-95МС з району Енгельса", None)[0]] == ["Енгельс"]


def test_zatoka_namesakes_2026_11_02():
    """02.11 15:57–16:01: «Бандероль → Затока» показали біля Чугуєва (скрін користувача)."""
    # підпис каналу й ім'я речника — не населені пункти
    assert not P.parse("Український Телеграм", "novini_ukrtg").places
    assert not P.parse("полковник Юрій Ігнат", "ppo_poltava").places
    # «в сторону Затоки» від одеського каналу — курортна Затока, а не село Затоки на Хмельниччині
    o = P.parse("Х-59 2 КАБ-и  Та до 6-7 бандеролєй   в сторону Затоки", "admiralbukhta", ctx=(46.45, 30.7))
    assert names(o, "t") == ["Затока"] and o.places[0].place.lat < 47
    # національний канал «на Затоку» з харківським контекстом: якщо бандеролі вже летять на одеську Затоку — це вони
    tr = Tracker(SOURCES, learn=False)
    t0 = 1_793_627_600.0
    tr.ingest(P.parse("Бандероли курс Затока", "odessa_knight", ctx=(46.45, 30.7)), "odessa_knight", t0)
    mk = P.parse('8 мКР "Бандероль та 2 Х-59, 2 авіабомби на Затоку.', "MK", ctx=(49.9, 36.3))
    tr.ingest(mk, "MK", t0 + 240)
    act = [x for x in tr.tracks if x.type == "banderol" and not x.closed and not x.merged]
    assert len(act) == 1  # одна ціль, а не друга біля Чугуєва
    lat = __import__("app.geo", fromlist=["from_xy"]).from_xy(*act[0].est(t0 + 240))[0]
    assert lat < 47.5, "бандероль має лишатися на півдні, а не біля Чугуєва"


def test_tsyrkuny_stale_course_2026_11_02():
    """02.11 15:42–15:48: «→ Циркуни» на шахеді, що «летів» на Богодухів (скрін користувача)."""
    # новина про удар — не нова ціль
    assert P.parse("⚡️У Черкаській Лозовій дрон атакував спецтехніку, є загиблі.", "CX").kind == "filtered"
    tr = Tracker(SOURCES, learn=False)
    t0 = 1_793_626_968.0
    tr.ingest(P.parse("Ударний БПЛА на Дергачі", "M"), "M", t0)
    tr.ingest(P.parse("Ударний БПЛА на Циркуни⚠️", "M"), "M", t0 + 600)
    snap = [x for x in tr.snapshot(t0 + 700)["tracks"] if x["type"] == "shahed"]
    assert len(snap) == 1
    s = snap[0]
    assert s["next"] != "Циркуни", "ціль уже в Циркунах — «→ Циркуни» не показуємо"


def test_no_context_prefers_significant_place():
    """02.11: національні канали без контексту — значущий пункт, а не тезка біля Харкова (старий умовний центр)."""
    from app.parser import Parser
    p = Parser()
    pl = lambda t, ch: [(r.place.name, round(r.place.lat, 1)) for r in p.parse(t, ch).places]
    assert pl("Затока там ще 2 КАБ-и летять Та штук 5 бандеролєй", "admiralbukhta") == [("Затока", 46.1)]  # 16:07, а не село на Харківщині
    assert pl("🫡 ХМЕЛЬНИЦЬКИЙ — відбій червоної тривоги!", "zahid_golovne_ua") == [("Хмельницький", 49.4)]
    assert pl("Реактивний БпЛА курсом на Запоріжжя", "KL") == [("Запоріжжя", 47.9)]
    assert pl("🔴⚠️Герань-5 падає на Рівне.", "MU") == [("Рівне", 50.6)]
    assert pl("🛵 Реактивний на Трипілля", "eRadarrua") == [("Трипілля", 50.1)]
    assert pl("КАБ на Золочів", None) == [("Золочів", 50.3)]  # КАБ — біля фронту (Харківщина), не Львівщина


def test_heading_learned_and_map_speed():
    """Бектест 26.10–02.11: без названого пункту курс з навчених маршрутів (медіана похибки 46° → 19°);
    на мапі ціль просувається з ефективною швидкістю (шахед ×0.35, реактивний ×0.6), а не паспортною."""
    import time
    from app import config
    from app.geo import bearing, dist_km, to_xy
    from app.parser import Parser
    from app.tracker import MAP_K, Tracker

    class B:
        def __init__(self, far=False):
            self.far = far

        def next_places(self, typ, name, heading=None, here=None):
            return [("Мерефа", 0.8, 49.82, 36.05)] if not self.far else [("Циркуни", 0.9, 50.08, 36.39)]

        def next_path(self, *a, **k):
            return []

        def rel(self, s, prior):
            return prior

        def __getattr__(self, n):
            return lambda *a, **k: None
    p = Parser()
    now = time.time()
    tr = Tracker(config.SOURCES, B(), learn=False)
    tr.ingest(p.parse("Шахед у районі Чугуєва"), "M", now - 600)
    t = tr.tracks[0]
    assert t.hd_src == "learned" and abs(((t.heading - bearing(t.last.place.xy, to_xy(49.82, 36.05))) + 540) % 360 - 180) < 1
    s = [x for x in tr.snapshot(now)["tracks"] if x["status"] == "active"][0]
    moved = dist_km(t.last.place.xy, to_xy(s["lat"], s["lon"]))
    from app.tracker import map_disp
    # модель показу: 10 хв шахеда ≈ 170·10/60·0.7 ≈ 19.8 км (бектест: k≈1.0 на 10 хв, 0.49 на 40 хв)
    assert abs(moved - map_disp("shahed", 170, 600)) < 2 and abs(moved - 19.8) < 2 and s["dm"] == [0.7, 0.5] and s["hd_src"] == "learned"
    assert abs(map_disp("shahed", 170, 2400) - 170 * 10 / 60 * 0.7 * 2) < 0.1  # 40 хв — лише вдвічі далі за 10 хв
    # навчений «наступний пункт» за 100+ км — не курс
    tr2 = Tracker(config.SOURCES, B(far=True), learn=False)
    tr2.ingest(p.parse("Шахед у районі Лозової"), "M", now)
    assert tr2.tracks[0].heading is None


def test_analyst_direction_and_likely_next():
    from app.analyst import direction_quality, likely_next, summary
    act = [{"id": "Ш-1", "type": "shahed", "lat": 49.6, "lon": 34.5, "hd": 270, "hd_src": "learned", "count": 2, "next": None, "pred_next": "Решетилівка", "pred_p": 0.6},
           {"id": "Ш-2", "type": "shahed", "lat": 49.5, "lon": 34.6, "hd": None, "count": 1, "next": None}]
    dq = direction_quality(act)
    assert dq == {"learned": 2, "none": 1}
    ln = likely_next(act)
    assert ln[0]["name"] == "Решетилівка" and ln[0]["n"] == 2
    r = {"active_n": 3, "active": {"shahed": 3}, "wave": {"new30": 0, "prev30": 0, "trend": "стабільна", "peak12h": 3},
         "corridors": [], "targets": [], "likely_next": ln, "direction": dq, "oblast_p60": [], "launches": [], "nights": None,
         "sources": [], "self": {"hd_acc": {"shahed": {"acc": 0.72, "n": 90}}}}
    txt = " ".join(summary(r))
    assert "Напрямок відомий для 2 з 3" in txt and "Решетилівка (2 цілі, 60%)" in txt and "шахед 72% з 90" in txt


def test_push_stages_like_israel():
    """Етапи сповіщень (як Home Front Command): «можлива загроза» → «курс на ваш район» → явний «відбій для вас»;
    під час масованої атаки — одне повідомлення на телефон за раз."""
    import asyncio
    from pathlib import Path as P_
    from app.geo import to_xy
    from app.push import Push, p_toward
    # калібровка: прямо на дім (40 км) — ~0.5; під 45° — ~0.15; під 120° — ~0
    assert 0.45 <= p_toward("channels", 0, 40) <= 0.75 and p_toward("channels", 120, 40) < 0.05
    H = to_xy(50.00, 36.23)
    straight = {"id": "Ш-1", "type": "shahed", "lat": 50.30, "lon": 36.23, "speed": 170, "hd": 180.0, "hd_src": "learned", "route": [], "count": 1, "status": "active", "conf": 0.9}
    side = dict(straight, id="Ш-2", hd=215.0)
    away = dict(straight, id="Ш-3", hd=0.0)
    assert Push.assess(straight, H)["stage"] == "threat"
    assert Push.assess(side, H)["stage"] == "pre"
    assert Push.assess(away, H)["stage"] is None
    sent = []

    class Cli:
        async def post(self, url, json=None, headers=None):
            sent.extend(json)

            class R:
                def json(self_):
                    return {"data": []}
            return R()
    pu = Push(P_(":memory:"))
    pu.db.execute("INSERT INTO subs VALUES('ExponentPushToken[abcdefghijkl]', 36.23, 50.0, 0)")
    many = [dict(straight, id=f"Ш-{i}") for i in range(10, 30)]
    asyncio.run(pu.tick(Cli(), {"tracks": many}))
    assert len(sent) == 1 and "20 цілей до вас" in sent[0]["title"]  # одне зведене, а не 20 сповіщень
    sent.clear()
    import time as _t
    for k in pu.armed["ExponentPushToken[abcdefghijkl]"]:
        pu.armed["ExponentPushToken[abcdefghijkl]"][k] = _t.time() - 300
    # канали замовкли (lost) — це не доказ, що загроза минула: відбою не надсилаємо
    asyncio.run(pu.tick(Cli(), {"tracks": [dict(t, status="lost") for t in many]}))
    assert sent == []
    # канали написали «збито / не фіксується» (closed) — тоді так
    asyncio.run(pu.tick(Cli(), {"tracks": [dict(t, status="closed") for t in many]}))
    assert len(sent) == 1 and "віддалились" in sent[0]["title"]


def test_area_stats(tmp_path):
    """«Ваш район» як архів Tzofar: цілі, що пройшли ≤ r км від дому, години, з якого боку, типи — за мапами доби."""
    import json as _j
    from app.areastats import area_stats
    t0 = 1_793_580_000  # 02.11 02:40 Київ; найближчий підхід ≈03:00
    day = {"tracks": [
        {"id": "Ш-1", "type": "shahed", "pts": [[36.23, 50.60, t0], [36.23, 50.30, t0 + 600], [36.23, 49.90, t0 + 1500]]},  # з півночі через Харків
        {"id": "РБ-1", "type": "jet", "pts": [[30.5, 50.4, t0], [30.6, 50.5, t0 + 300]]}]}                                  # Київ — далеко
    (tmp_path / "2026-11-02.json").write_text(_j.dumps(day), encoding="utf-8")
    r = area_stats(50.0, 36.23, 25, 14, tmp_path)
    assert r["total"] == 1 and r["types"] == {"shahed": 1} and r["sides"] == {"півночі": 1}
    assert sum(r["hours"]) == 1 and r["hours"][3] == 1


def test_visits_counter(tmp_path):
    """Лічильник відвідувань: унікальні за добу без збереження IP; боти не рахуються; старі хеші видаляються."""
    from app.visits import Visits
    v = Visits(tmp_path / "v.sqlite")
    t = 1_793_620_000
    v.hit("1.2.3.4", "Mozilla/5.0 iPhone", "view", t)
    v.hit("1.2.3.4", "Mozilla/5.0 iPhone", "view", t + 60)
    v.hit("5.6.7.8", "Mozilla/5.0 Android", "ws", t + 120)
    v.hit("9.9.9.9", "Googlebot/2.1", "view", t)
    rows = v.db.execute("SELECT uniq, views, ws FROM day").fetchall()
    assert rows == [(2, 2, 1)]
    assert not any("1.2.3.4" in str(r) for r in v.db.execute("SELECT * FROM seen").fetchall())
    v.hit("1.2.3.4", "Mozilla/5.0 iPhone", "view", t + 86400)
    assert v.db.execute("SELECT COUNT(*) FROM seen WHERE d < (SELECT MAX(d) FROM day)").fetchone()[0] == 0
    assert v.stats()["total_visitor_days"] == 3


def test_webpush_subscribe_and_stage_send(tmp_path, monkeypatch):
    """Web Push для сайту/PWA: підписка з координатами дому, ті самі етапи, що й у застосунку; 410 — підписку прибрано."""
    import asyncio
    import app.push as pushmod
    from app.push import Push
    monkeypatch.setattr(pushmod, "VAPID_KEY", tmp_path / "vapid.pem")
    pu = Push(tmp_path / "push.sqlite")
    assert len(pu.public_key()) == 87 and (tmp_path / "vapid.pem").exists()
    sub = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": "BPk", "auth": "x1"}}
    assert not pu.web_register({"endpoint": "http://evil"}, 36.23, 50.0)
    assert not pu.web_register(sub, 2.35, 48.85)  # не Україна
    assert pu.web_register(sub, 36.23, 50.0) and pu.count() == 1
    got = []

    async def fake(s, payload):
        got.append((s["endpoint"], payload))
        return 410

    pu.web_sender = fake
    tr = {"id": "Ш-1", "type": "shahed", "lat": 50.30, "lon": 36.23, "speed": 170, "hd": 180.0, "hd_src": "learned",
          "route": [], "count": 1, "status": "active", "conf": 0.9}

    class Cli:
        async def post(self, *a, **k):
            raise AssertionError("Expo не має викликатися для веб-підписок")
    asyncio.run(pu.tick(Cli(), {"tracks": [tr]}))
    assert len(got) == 1 and got[0][1]["title"][:1] in "🔴🟠" and "Шахед" in got[0][1]["title"]
    assert pu.count() == 0  # 410 Gone — браузер скасував підписку


def test_launch_forecast_and_ship_carrier_2026_11_02():
    """02.11 21:00: «ПУСК: балістика з Курськ (кораблі (Калібр))» — з посту-попередження «ворог може застосовувати…»."""
    from app.launch import LaunchBook, detect
    warn = ("❗Друзі, маю попередження, що ворог може застосовувати: Значну кількість шахедів ❗️Балістичні ракети з Курська, "
            "Брянська, Воронежа ❗️Ракети зі стратегічної авіації Х-10, Калібри з кораблів")
    assert detect(warn, "ballistic")[0] == []
    assert detect("40 балістичних ракет із Курська, Брянська (не думаю, що всі будуть застосовані)", "ballistic")[0] == []
    # справжній пуск: носій «кораблі» з іншої частини посту не приписуємо аеродрому
    sites, typ, car, summ = detect("Пуск балістики з Курська! Також Калібри з кораблів", "ballistic")
    assert [s.name for s in sites] == ["Курськ (Халіно)"]
    L = LaunchBook().add(sites, "ballistic", None, car, "x", None, 1_793_646_000.0, summ)[0]
    assert not L.carrier or "Калібр" not in L.carrier


def test_state_smoke():
    """state() — те, що отримують усі клієнти; падіння тут = мапа без даних (02.11 21:38: 500 після винесення доказів)."""
    import os
    os.environ.setdefault("REPLAY", "1")
    from app import main as M
    M.tracker.ingest(P.parse("Ударний БПЛА на Дергачі", "M"), "M")
    s = M.state()
    assert s["tracks"] and "items" not in s["tracks"][0]["ev"]
    assert M.tracker.track_evidence(s["tracks"][0]["id"])["items"]


def test_history_lite_and_frame():
    """Машина часу: легкі кадри без публікацій, повний кадр — окремо і лише «не пізніше» запитаного моменту."""
    import json as _j
    from app import main as M
    M.HIST[:] = [{"t": 1000, "levels": {}, "raions": {}, "tracks": [{"id": "Ш-1", "ev": {"pubs": 1, "prim": ["M"], "items": [{"t": 990, "src": "M"}]}}]},
                 {"t": 1060, "levels": {}, "raions": {}, "tracks": [{"id": "Ш-1", "ev": {"pubs": 2, "prim": ["M", "K"], "items": [{"t": 1050, "src": "K"}]}}]}]
    import time as _t
    old = _t.time
    _t.time = lambda: 1100
    try:
        lite = _j.loads(M.api_history().body)["frames"]
    finally:
        _t.time = old
    assert len(lite) == 2 and "items" not in lite[0]["tracks"][0]["ev"] and lite[0]["tracks"][0]["ev"]["prim"] == ["M"]
    fr = _j.loads(M.api_history_frame(1010).body)
    assert fr["t"] == 1000 and fr["tracks"][0]["ev"]["items"][0]["src"] == "M"  # пізніше повідомлення K ще не видно
    M.HIST.clear()


def test_changes_digest():
    """«Що змінилося»: тривога оголошена, нова ціль з перепостами, курс уточнено (хто), втрачена позначка — не відбій."""
    from app.changes import changes
    H = (36.25, 50.0)
    t0 = 1_793_600_000
    frames = [{"t": t0, "levels": {}, "raions": {}, "tracks": [
        {"id": "Ш-1", "type": "shahed", "lat": 50.3, "lon": 36.25, "hd": 180.0, "next": "Дергачі"},
        {"id": "Ш-2", "type": "shahed", "lat": 49.8, "lon": 36.0, "hd": 90.0, "next": None}]},
        {"t": t0 + 300, "levels": {"Харківська": 1}, "raions": {}, "tracks": []}]
    now = {"now": t0 + 720, "levels": {"Харківська": 1}, "official": {"raion_levels": {}}, "tracks": [
        {"id": "Ш-1", "type": "shahed", "lat": 50.15, "lon": 36.25, "hd": 180.0, "next": "Харків", "status": "active", "first": t0 - 600, "last": t0 + 700},
        {"id": "Ш-2", "type": "shahed", "lat": 49.8, "lon": 36.0, "hd": 90.0, "status": "lost", "last": t0 + 60},
        {"id": "Ш-3", "type": "shahed", "lat": 50.2, "lon": 36.6, "hd": 230.0, "status": "active", "first": t0 + 500, "last": t0 + 500,
         "count": 2, "ev": {"pubs": 5, "indep": 1, "prim": ["KL"]}}]}
    ev_of = lambda tid: {"items": [{"t": t0 + 650, "src": "R", "why": "змінило курс", "dest": "Харків"}]} if tid == "Ш-1" else {}
    r = changes(frames, now, *H, since=t0 + 10, names={"shahed": "Шахед"}, ev_of=ev_of, obl="Харківська")
    k = [e["k"] for e in r["events"]]
    assert k[0] == "official" and "тривогу" in r["events"][0]["text"] and r["events"][0]["t"] == t0 + 300
    new = next(e for e in r["events"] if e["k"] == "new")
    assert "Одне першоджерело" in new["text"] and "повторили ще 4" in new["text"]
    crs = next(e for e in r["events"] if e["k"] == "course")
    assert "було → Дергачі" in crs["text"] and "тепер → Харків" in crs["text"] and "R о" in crs["text"]
    lost = next(e for e in r["events"] if e["k"] == "lost")
    assert "не відбій" in lost["text"]


def test_source_direction_reliability():
    """Точність напрямку каналу вчиться онлайн; суперечлива версія від менш точного каналу не перебиває курс."""
    from pathlib import Path as P_
    from app.brain import Brain
    b = Brain(P_(":memory:"))
    for _ in range(30):
        b.pred_score("dir:GOOD", True)
    for _ in range(30):
        b.pred_score("dir:BAD", False)
    g, ng = b.dir_rel("GOOD")
    bad, _ = b.dir_rel("BAD")
    assert ng == 30 and g > 0.9 and bad < 0.25 and b.dir_rel("NEW")[0] == b.DIR_PRIOR
    tr = Tracker(SOURCES, b, learn=False)
    t0 = 1_793_600_000.0
    tr.ingest(P.parse("Шахед у районі Чугуєва курсом на Харків", "M"), "GOOD", t0)
    rec = tr.ingest(P.parse("Шахед у районі Чугуєва курсом на Балаклію", "M"), "BAD", t0 + 60)
    t = tr.tracks[0]
    assert t.route and t.route[0].name == "Харків" and rec.get("kept_version") == "GOOD"


def test_kyiv_kharkivskyi_masyv_2026_11_02():
    """02.11 22:37: «шахед над Києвом курсом на Харківський масив» — показали шахед за 8 км від дому в Харкові (4 канали)."""
    for t, ch in [("⚠️Звичайний шахед над Києвом курсом на Харківський масив, Позняки.", "MU"),
                  ("Герань на Харківський масив, Київ!", "Ukrainian_Intelligence"),
                  ("БпЛА над Києвом повз Харківський масив", "kiev_nebo")]:
        o = P.parse(t, ch)
        assert o.places and all("(Київ)" in r.place.name or r.place.name == "Київ" for r in o.places), (t, names(o))
    assert names(P.parse("Шахед на Харків", "K")) == ["Харків"]


def test_course_only_target_has_no_position():
    """«Шахед на Харків» без місця: позначка — оцінка, не місце; push — «курс на ваш район» без вигаданих км/хв."""
    from app.geo import to_xy
    from app.push import Push
    tr = Tracker(SOURCES, learn=False)
    tr.ingest(P.parse("Шахед курсом на Харків", "K"), "K", 1_793_600_000.0)
    s = [x for x in tr.snapshot(1_793_600_060.0)["tracks"]][0]
    assert s["nopos"] is True
    a = Push.assess(dict(s, route=[[36.23, 49.99]]), to_xy(50.0, 36.25))
    assert a and a["stage"] == "threat" and a["d"] is None and a["eta"] is None
    assert Push.assess(dict(s, route=[[30.5, 50.45]]), to_xy(50.0, 36.25)) is None  # курс на Київ — не загроза Харкову


def test_repost_does_not_refresh_track():
    """Перепост того самого тексту іншим каналом через 10 хв не скидає годинник цілі (хибна свіжість)."""
    from app.parser import Parser
    from app.tracker import Tracker
    from app.config import SOURCES
    P, trk = Parser(), Tracker(SOURCES)
    txt = "Шахед у районі Чугуєва, рухається курсом на Харків"
    o = P.parse(txt, "K"); o.raw = txt
    trk.ingest(o, "K", 1000.0, None)
    tr = trk.tracks[0]
    o2 = P.parse(txt, "D"); o2.raw = txt
    rec = trk.ingest(o2, "D", 1600.0, None)
    assert rec.get("copy_of") == "K"
    assert tr.last.t == 1000.0
    assert tr.evidence[-1]["why"] == "перепост"


def test_strategic_takeoff_is_not_launch():
    """«Зліт Ту-95МС» — носії в повітрі, не пуск: кількість — борти, ракети до нього не прив'язуються."""
    from app import launch
    from app.parser import Parser
    P, lb = Parser(), launch.LaunchBook()
    t = "Зліт 7 Ту-95МС з аеродрому Оленья"
    sites, typ, car, summ = launch.detect(t, P.parse(t, "K").type)
    L = lb.add(sites, typ, 7, car, "K", "https://t.me/x/1", 1000.0, summ, t)[0]
    assert L.stage == "takeoff" and L.srcs == {"K"} and L.links
    t2 = "Пуски Х-101 з Ту-95МС з району Оленьї"
    sites2, typ2, car2, _ = launch.detect(t2, "cruise")
    if sites2 and sites2[0] is sites[0]:
        L2 = lb.add(sites2, typ2, None, car2, "D", None, 1500.0, False, t2)[0]
        assert L2 is L and L.stage == "launch" and L.count is None
    snap = lb.snapshot(1600.0)
    assert snap[0]["stage"] in ("takeoff", "launch")


def test_launch_not_linked_to_target_flying_back():
    """Шахед біля Люботина летить на північ (на Польову) — не прив'язуємо його до пуску з Орла (на півночі)."""
    from app.parser import Parser
    from app.tracker import Tracker
    from app.config import SOURCES
    from app import launch
    P, trk = Parser(), Tracker(SOURCES)
    t0 = "Пуск шахедів з Орла"
    sites, typ, car, summ = launch.detect(t0, "shahed")
    trk.launches.add(sites, typ, None, car, "K", None, 1000.0, summ, t0)
    txt = "Шахед біля Люботина курсом на Польову"
    o = P.parse(txt, "K"); o.raw = txt
    trk.ingest(o, "K", 1000.0 + 3 * 3600, None)
    tr = trk.tracks[0]
    L = trk.launches.link(tr, 1000.0 + 3 * 3600 + 60)
    assert not L or L.get("est") or L.get("site") != "Орел"


def test_lancet_clear_does_not_close_other_targets():
    """«По ланцету чисто» закриває лише «Ланцет», а не шахеда поруч."""
    from app.parser import Parser
    from app.tracker import Tracker
    from app.config import SOURCES
    P, trk = Parser(), Tracker(SOURCES)
    for txt, t in [("Шахед над Вільнянськом", 1000.0), ("Ланцет над Вільнянськом", 1010.0), ("Вільнянськ, у вас по ланцету чисто", 1100.0)]:
        o = P.parse(txt, "shovnebi"); o.raw = txt
        trk.ingest(o, "shovnebi", t, None)
    sh = [x for x in trk.tracks if x.type == "shahed"]
    la = [x for x in trk.tracks if x.type == "lancet"]
    assert sh and not sh[0].closed
    assert la and la[0].closed


def test_damage_report_is_not_a_target():
    from app.parser import Parser
    o = Parser().parse("▪️у Харківському районі пошкоджено вантажний автомобіль, цивільне підприємство, електромережі (сел. Пересічне), господарчі споруди", "SG")
    assert o.kind != "track"


def test_push_near_target_without_course_is_threat():
    """Шахед за ~5 км від дому з невідомим курсом — загроза (раніше push мовчав)."""
    from app.push import Push
    from app.geo import to_xy
    a = Push.assess({"lat": 50.03, "lon": 36.30, "speed": 170, "hd": None, "route": [], "type": "shahed"}, to_xy(49.99, 36.27))
    assert a and a["stage"] == "threat" and a["eta"] is None


def test_nickname_and_hypothetical_threat_not_a_target():
    """«Міхалич, …щоб в разі загрози балістики…» — ім'я й умовна фраза, а не балістика в Михальче."""
    from app.parser import Parser
    o = Parser().parse("Міхалич, зніми червону тривогу для столиці, щоб в разі загрози балістики повторно увімкнути і розбудити людей", "eRadarrua")
    assert o.kind != "track" and not any(p.place.name == "Михальче" for p in o.places)


def test_russian_cities_not_ukrainian_namesakes():
    """«з Брянська», «з Курська», «з Орла» — міста РФ, не кримські Брянське/Курське і не Орел на Одещині."""
    from app.parser import Parser
    P = Parser()
    for t in ("Загроза балістики з Брянська", "Шахеди з Курська на Суми", "Шахед з Орла на Глухів"):
        names = [p.place.name for p in P.parse(t, "K").places]
        assert not set(names) & {"Брянське", "Курське", "Орел"}, (t, names)
    assert any(p.place.name == "Орлівка" for p in P.parse("Орлівка, шахед", "K").places)


def test_tracker_state_roundtrip():
    """Стан трекера переживає перезапуск: ті самі цілі, пуски з тими самими місцями (тотожність Site)."""
    from app.parser import Parser
    from app.tracker import Tracker
    from app.config import SOURCES
    from app import launch
    import time as _t
    P, a = Parser(), Tracker(SOURCES)
    now = _t.time()
    o = P.parse("Шахед біля Люботина курсом на Польову", "K"); o.raw = "x"
    a.ingest(o, "K", now - 60, None)
    s_, ty, car, sm = launch.detect("Пуск шахедів з Орла", "shahed")
    a.launches.add(s_, ty, None, car, "K", None, now - 120, sm, "Пуск шахедів з Орла")
    b = Tracker(SOURCES)
    assert b.load_state(a.dump_state())
    assert [t.id for t in b.tracks] == [t.id for t in a.tracks]
    assert b.launches.items and b.launches.items[0].site is launch.SITE_LIST[[x.name for x in launch.SITE_LIST].index("Орел")]
    assert not Tracker(SOURCES).load_state(a.dump_state(), max_age=-1)


def test_channel_signature_is_not_air_defense_report():
    """«🇺🇦 ППО Полтава» — підпис каналу; сам рядок не робить повідомлення «роботою ППО», а назви з малої читаються."""
    from app.parser import Parser
    o = Parser().parse("Заїченці курс в’язівок\n\n🇺🇦 ППО Полтава", "ppopoltavanightfighters")
    assert o.kind != "filtered" and [p.place.name for p in o.places] == ["Заїченці", "В’язівок"]
    assert Parser().parse("Шахед збито над Полтавою", "ppopoltavanightfighters").kind == "filtered"


def test_forecast_journal_logs_candidates_and_truth():
    from pathlib import Path
    from app.brain import Brain
    from app.tracker import Tracker
    from app.config import SOURCES
    from app.parser import Parser
    b = Brain(Path(":memory:")); trk = Tracker(SOURCES, b); P = Parser()
    for txt, t in [("Шахед біля Мерефи", 1000.0), ("Шахед біля Люботина", 1900.0), ("Шахед біля Пересічного", 2800.0)]:
        o = P.parse(txt, "K"); o.raw = txt; trk.ingest(o, "K", t, None)
    rows = b.db.execute("SELECT type, cand, truth FROM fcast").fetchall()
    assert rows and rows[0][0] == "shahed" and '"mv"' in rows[0][1]


def test_fusion_stays_off_without_data_and_turns_on_with_proven_gain():
    import json, random, sqlite3, time
    from app import fusion
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE fcast(t REAL, type TEXT, src TEXT, cand TEXT, truth REAL, dt REAL, d REAL)")
    assert fusion.evaluate(db)["on"] is False
    random.seed(1); now = time.time()
    for i in range(2000):  # «показаний» курс шумний (±60°), навчений маршрут точний (±10°)
        tr = random.uniform(0, 360)
        c = {"cur": (tr + random.gauss(0, 60)) % 360, "ln": (tr + random.gauss(0, 10)) % 360, "mv": (tr + random.gauss(0, 40)) % 360}
        db.execute("INSERT INTO fcast VALUES(?,?,?,?,?,?,?)", (now - (i % 8) * 86400 - 3600, "shahed", "K", json.dumps(c), tr, 600, 20))
    rep = fusion.evaluate(db, now)
    assert rep["on"] is True and rep["by_type"]["shahed"]["fused"]["med"] < rep["by_type"]["shahed"]["current"]["med"]


def test_webpush_test_endpoint_rejects_unknown_device():
    from fastapi.testclient import TestClient
    from app.main import app
    r = TestClient(app).post("/api/webpush/test", json={"endpoint": "https://unknown.example/x"})
    assert r.status_code == 404


def test_zone_push_aggregated_and_rate_limited(tmp_path, monkeypatch):
    """Push для обраних областей: одне зведення на кілька цілей, не частіше разу на 5 хв, без повторів про ту саму ціль."""
    import asyncio
    import app.push as pushmod
    from app.push import Push
    monkeypatch.setattr(pushmod, "VAPID_KEY", tmp_path / "vapid.pem")
    pu = Push(tmp_path / "push.sqlite")
    sub = {"endpoint": "https://fcm.googleapis.com/fcm/send/z1", "keys": {"p256dh": "BPk", "auth": "x1"}}
    assert pu.web_register(sub, 36.23, 50.0, True, {"obl": ["Полтавська"], "hrom": []})  # дім у Харкові, зона — Полтавщина
    got = []

    async def fake(s, payload):
        got.append(payload)
        return 201
    pu.web_sender = fake

    def tr(i, lat, lon):
        return {"id": f"Ш-{i}", "type": "shahed", "lat": lat, "lon": lon, "speed": 170, "hd": None, "hd_src": None,
                "route": [], "count": 1, "status": "active", "conf": 0.9, "ev": {"prim": ["K"]}}
    class Cli:
        async def post(self, *a, **k):
            raise AssertionError
    asyncio.run(pu.tick(Cli(), {"tracks": [tr(1, 49.59, 34.55), tr(2, 49.07, 33.42)]}))  # Полтава, Кременчук
    assert len(got) == 1 and "Полтавська обл." in got[0]["title"] and "2" in got[0]["title"]
    asyncio.run(pu.tick(Cli(), {"tracks": [tr(1, 49.59, 34.55), tr(2, 49.07, 33.42), tr(3, 50.0, 33.0)]}))
    assert len(got) == 1  # нова ціль за хвилину — чекає 5 хв, а ті самі не повторюються


def test_daily_served_from_disk_without_rebuild(tmp_path, monkeypatch):
    """Після перезапуску мапа доби віддається з диска одразу, без перебудови (люди не чекають «Збираю маршрути…»)."""
    import asyncio, json, time
    import app.daily as dm
    monkeypatch.setattr(dm, "OUT", tmp_path)
    d = dm.Daily(None, None, None, None, [])
    day = "2026-11-03"
    (tmp_path / f"{day}.json").write_text(json.dumps({"v": dm.VER, "day": day, "final": True, "built": int(time.time()), "tracks": [], "booms": [], "crawl": 1}))
    async def boom(*a, **k):
        raise AssertionError("не мало перебудовувати")
    monkeypatch.setattr(dm, "build", boom)
    r = asyncio.run(d.get(day))
    assert r["day"] == day and r["final"] is True


def test_launch_marker_expires_by_flight_time():
    """03.11: «ПУСК: крилаті ракети з Бєлгорода · 05:37» висіла на мапі о 10:47. Позначка живе стільки, скільки зброя може летіти."""
    from types import SimpleNamespace as N
    from app import launch
    L = N(stage="launch", type="cruise", site=N(lat=50.6, lon=36.6))
    assert 1.5 * 3600 < launch.ttl(L) < 2.5 * 3600
    B = N(stage="launch", type="ballistic", site=N(lat=50.6, lon=36.6))
    assert launch.ttl(B) <= 20 * 60
    T = N(stage="takeoff", type=None, site=N(lat=48.5, lon=46.0))
    assert launch.ttl(T) == 3 * 3600


def test_passed_place_is_position():
    """TLK 03.11: «Пролетела Печенеги, курс на Шестаково» — Печеніги це де ціль була, Шестакове це курс."""
    o = P.parse("Пролетела Печенеги, курс на Шестаково⚠️", "TLK")
    roles = {r.place.name: r.role for r in o.places}
    assert roles.get("Печеніги") == "p" and roles.get("Шестакове") == "t"


def test_sw_shell_no_duplicates():
    """03.11: дубль у SHELL → cache.addAll відхиляє встановлення, служба не стартує, push мертвий."""
    import re, pathlib
    s = (pathlib.Path(__file__).parent.parent / "web" / "sw.js").read_text()
    shell = re.findall(r"'(/[^']*)'", re.search(r"SHELL=\[(.*?)\]", s).group(1))
    assert len(shell) == len(set(shell))
    assert "addAll(SHELL)" not in s


def test_push_only_real_threat_within_40km():
    """03.11 калібрування: «курс на вас» з 80–150 км справджувався в 1,4%. Телефон турбуємо лише в межах 40 км."""
    import asyncio
    from pathlib import Path as P_
    from app.push import Push
    sent = []

    class Cli:
        async def post(self, url, json=None, headers=None):
            sent.extend(json)

            class R:
                def json(self_):
                    return {"data": []}
            return R()
    far = {"id": "Ш-far", "type": "shahed", "lat": 50.80, "lon": 36.23, "speed": 170, "hd": 180.0, "hd_src": "channels", "route": [], "count": 1, "status": "active", "conf": 0.9}
    near = dict(far, id="Ш-near", lat=50.30)
    pu = Push(P_(":memory:"))
    pu.db.execute("INSERT INTO subs VALUES('ExponentPushToken[abcdefghijkl]', 36.23, 50.0, 0)")
    asyncio.run(pu.tick(Cli(), {"tracks": [far]}))
    assert sent == []  # ~89 км: лише на мапі
    asyncio.run(pu.tick(Cli(), {"tracks": [near]}))
    assert len(sent) == 1 and sent[0]["title"].startswith(("🟠", "🔴"))


def test_aftermath_is_not_target():
    """03.11 monitor 1654: «Так виглядає міська клінічна лікарня після ракетного удару у Харкові» стало ракетою на Харків."""
    for t in ["Так виглядає міська клінічна лікарня після ракетного удару у Харкові.", "Наслідки нічної атаки на Харків",
              "ЛПДС «Самара» після чергової атаки БПЛА 🔥"]:
        o = P.parse(t, "M")
        assert o.no_target and o.type is None, t
    assert P.parse("Шахед на Харків, після удару ще один курсом на Чугуїв", "M").type == "shahed"
    assert P.parse("Ракета на Харків!", "M").type == "cruise"


def test_app_installs_counted(tmp_path):
    from app.visits import Visits
    v = Visits(tmp_path / "v.sqlite")
    v.app_hit("1.1.1.1", "Mozilla", "app"); v.app_hit("1.1.1.1", "Mozilla", "app"); v.app_hit("2.2.2.2", "Mozilla", "install")
    d = v.stats(1)["days"][-1]
    assert d["app_users"] == 1 and d["installs"] == 1 and d["visitors"] == 0


def test_kab_namesakes_near_front():
    """03.11: «КАБ на Запоріжжя» ставило загрозу в село Запоріжжя під Дніпром; «СУшки» ставали селом, «кабельна лінія» КАБом."""
    o = P.parse("💣 КАБи на Запоріжжя.", "K")
    assert o.type == "kab" and abs(o.places[0].place.lat - 47.85) < 0.1
    assert not P.parse("СУшки в бнр, угроза КАБ⚠️", "R").places
    assert P.parse("Через аварію на кабельній лінії знеструмлено абонентів у Чернігові.", "horizon_of_war_Official").type is None
    assert not P.parse("Південний схід області: тактична тактика на КАБи", "DN").places


def test_defense_forces_not_place():
    """03.11 deraketaua: «В ніч на 3 листопада Сили оборони знищили:» стало балістикою на село Сила."""
    o = P.parse("🔱В ніч на 3 листопада Сили оборони знищили:", "deraketaua")
    assert o.type is None and not o.places
    assert P.parse("Ситуація станом на 00:43: • Р-Шахед на Близнюки", "shovnebi").type is not None


def test_common_words_not_places():
    """Аудит журналу 03.11: колір тривоги, «триває», «серед», вулиці, «Нова пошта» ставали селами."""
    for src, t in [("DN", "Над Дніпром реактивний. Червоний 🟥."), ("DN", "Для нас поки без загроз. Жовтий для всієї області 🟨"),
                   ("MU", "Триває загроза балістики з Таганрогу."), ("M", "Реактивний Шахед продовжує рух на вул. Світла❗️"),
                   ("SU", "Молнія на Проспект Перемоги"), ("TRK", "⚡️ «Нова пошта» оголосила про запуск")]:
        names = [r.place.name for r in P.parse(t, src).places]
        assert not set(names) & {"Червоне", "Жовте", "Тривайли", "Світле", "Перемога", "Нова"}, (t, names)
    assert "Червоне" in [r.place.name for r in P.parse("⚠️ Реактивный от Студенок на Червоное, Лозовую", "ND").places]
    assert "Зелений Колодязь" in [r.place.name for r in P.parse("Реактивний БПЛА на Зелений Колодязь‼️", "M").places]
    assert "Харків" in [r.place.name for r in P.parse("Шахед залетел, курс Новые Дома", "R").places]


def test_kharkiv_districts_russian_forms():
    """Аудит 03.11: «на Северную Салтовку» ставило ціль у Сєверне на окупованій Донеччині."""
    names = [r.place.name for r in P.parse("Шахед курсом на Северную Салтовку", "D").places]
    assert "Сєверне" not in names and "Північна Салтівка (Харків)" in names
    assert [r.place.name for r in P.parse("Реактивный шахед на Новую Баварию", "D").places] == ["Нова Баварія (Харків)"]


def test_official_alert_push_home(monkeypatch):
    """Офіційна тривога й відбій для громади дому, з затримкою 45 с: «відбій і знову тривога за 20 с» не дає двох сповіщень."""
    import asyncio
    from pathlib import Path as P_
    from app import push as pm
    sent = []

    class Cli:
        async def post(self, url, json=None, headers=None):
            sent.extend(json)

            class R:
                def json(self_):
                    return {"data": []}
            return R()
    pu = pm.Push(P_(":memory:"))
    pu.db.execute("INSERT INTO subs VALUES('ExponentPushToken[abcdefghijkl]', 36.23, 50.0, 0)")
    pu.home_area["ExponentPushToken[abcdefghijkl]"] = (7, "Харківська", "Харківський р-н", "Харківська")
    t = [1000.0]
    monkeypatch.setattr(pm.time, "time", lambda: t[0])
    snap = lambda h: {"tracks": [], "levels": {}, "official": {"ok": True, "updated": t[0], "hromadas": {7: 2} if h else {}, "raion_levels": {}}}
    asyncio.run(pu.tick(Cli(), snap(False)))          # перший погляд: тиша
    t[0] += 10; asyncio.run(pu.tick(Cli(), snap(True)))   # тривога почалась
    t[0] += 20; asyncio.run(pu.tick(Cli(), snap(True)))   # ще не 45 с
    assert sent == []
    t[0] += 30; asyncio.run(pu.tick(Cli(), snap(True)))
    assert len(sent) == 1 and sent[0]["title"].startswith("🔴 Повітряна тривога")
    t[0] += 10; asyncio.run(pu.tick(Cli(), snap(False)))  # відбій…
    t[0] += 15; asyncio.run(pu.tick(Cli(), snap(True)))   # …і знову тривога за 15 с
    t[0] += 60; asyncio.run(pu.tick(Cli(), snap(True)))
    assert len(sent) == 1  # нового сповіщення немає: стан не змінився


def test_maplibre_one_version_everywhere():
    """Головна мапа й мапа доби на одній версії MapLibre (03.11: оновлення 5.1 → 5.24)."""
    import re, pathlib
    vers = set()
    for f in pathlib.Path(__file__).resolve().parent.parent.joinpath("web").glob("*.html"):
        vers |= set(re.findall(r"maplibre-gl@([0-9.]+)", f.read_text(encoding="utf-8")))
    assert vers == {"5.24.0"}


def test_no_zoom_inside_match_for_raion_lines():
    """03.11: межі районів з тривогою не малювались з 02.11, бо zoom-інтерполяція була всередині match."""
    import pathlib
    s = pathlib.Path(__file__).resolve().parent.parent.joinpath("web", "app.js").read_text(encoding="utf-8")
    i = s.index("id:'ra-line'"); line = s[i:s.index("\n", i)]
    assert "['match',LV,0,['interpolate'" not in line


def test_no_has_filters_in_map_layers():
    """03.11: у MapLibre 5.24 властивість зі значенням undefined проходить ['has', ...], і на мапі
    з'являлись порожні чорні плашки «→». Фільтри мають перевіряти значення: ['!=',['get',k],null]."""
    import pathlib, re
    s = pathlib.Path(__file__).resolve().parent.parent.joinpath("web", "app.js").read_text(encoding="utf-8")
    assert not re.search(r"\[\s*'has'\s*,", s)


def test_oblast_adjective_list_is_not_a_route():
    """03.11, sectorv666: перелік областей прикметниками («Дніпропетровська» ≠ Дніпро, «Запорізька» ≠ село Запорізьке).
    Балістика з Таганрога не має «летіти» з Дніпра на Донецьк."""
    t = ("🚀 [03.11.2026 20:46] Загроза балістики з Таганрог: загроза для Донецька, Луганська, Запорізька, "
         "Дніпропетровська, Харківська, Полтавська, Херсонська, Миколаївська.")
    o = P.parse(t, "X")
    assert o.type == "ballistic" and o.places == [] and o.threat
    # родовий міст лишається містами
    o = P.parse("Шахед з Донецька на Луганськ", "X")
    assert [r.place.name for r in o.places] == ["Донецьк", "Луганськ"]


def test_ballistic_fast_target_and_false_places():
    """03.11 журнал: «швидкісна (ціль) на X» — балістика (DN, Shturval_media); «Зеленський» ≠ Зелень;
    «Воронєж» (РФ) ≠ Вороніж на Сумщині; реклама «Київський Іван» ≠ Київське, Іванів."""
    o = P.parse("На Харківщині швидкісні в напрямку м. Харків, тривожаться 7 областей.", "DN")
    assert o.type == "ballistic" and [r.place.name for r in o.places] == ["Харків"]
    o = P.parse("Швидкісна на Одесу", "Shturval_media")
    assert o.type == "ballistic" and [r.place.name for r in o.places] == ["Одеса"]
    o = P.parse("⚠️ За інформацією розвідки, російські війська готуються до чергових ударів балістичними ракетами, — Зеленський.", "TRK")
    assert o.places == []
    assert P.parse("Воронєж загроза балістики", "SU").places == []
    assert P.parse("Єдиний шлях, яким чином раніше усіх знати, що до нас летить балістика — слідкувати за Київським Іваном — @kyiv_vanek", "X").places == []
    assert [r.place.name for r in P.parse("Балістика на Вороніж (Сумщина)", "X").places] == ["Вороніж"]


def test_kryvyi_rih_cases():
    """03.11 журнал: «над Кривим Рогом» давало села Криве й Ріг; «Криворіжжя» (DN) село на Донеччині; «К.Ріг», «Кр Ріг»."""
    for t in ["🏍 Реактивний БпЛА над Кривим Рогом. Перебувайте в укриттях!", "Криворіжжя на звичайний мопед з Кіровоградської обл.",
              "Балістика на К.Ріг", "Балістика на Кр Ріг", "Шахед у Кривому Розі"]:
        assert [r.place.name for r in P.parse(t, "X").places] == ["Кривий Ріг"], t


def test_ballistic_threat_mode_events():
    """Режим балістичної загрози (03.11): сервер віддає, які області названо; відбій позначено окремо."""
    import time
    from app.tracker import bal_oblasts
    assert bal_oblasts("Загроза балістики з Таганрог: загроза для Донецька, Луганська, Запорізька, Дніпропетровська, Харківська.") == \
        ["Донецька", "Луганська", "Запорізька", "Дніпропетровська", "Харківська"]
    assert bal_oblasts("Загроза балістики для Харківщини та Сумщини") == ["Харківська", "Сумська"]
    p, tr = Parser(), Tracker(SOURCES)
    now = time.time()
    for i, t in enumerate(["Загроза балістики для Харківщини та Сумщини", "Балістика на Харків", "Відбій загрози балістики"]):
        o = p.parse(t, "X"); o.raw = t
        tr.ingest(o, "X", now + i, None)
    b = tr.snapshot(now + 5)["bal"]
    assert [e["obl"] for e in b] == [["Харківська", "Сумська"], ["Харківська"], []]
    assert [e["close"] for e in b] == [False, False, True]


def test_recon_with_lancet_threat_is_recon():
    """03.11: «Зала (угроза ланцет)»: ZALA розвідник, що може наводити Ланцет; Ланцет поруч не підтверджено."""
    o = P.parse("Зала (угроза ланцет) от Староверовки на Шевченково", "X")
    assert o.type == "recon" and o.pair == "lancet"
    assert [r.place.name for r in o.places] == ["Старовірівка", "Шевченкове"]
    assert P.parse("Ланцет на Шевченково", "X").type == "lancet"


def test_olshany_kharkiv_and_launchers_activity():
    """03.11 TLK: «Ракета Золочев/Ольшаны» (селище під Харковом не було в газетирі; 37 повідомлень у журналі),
    «Активність пускових» (Харків life, TLK) — попередження про балістику для області каналу."""
    o = P.parse("Ракета Золочев/Ольшаны⚠️", "TLK")
    assert [r.place.name for r in o.places] == ["Золочів", "Ольшани"]
    assert abs(o.places[1].place.lat - 50.05) < 0.1
    assert P.parse("Активність пускових", "X").type == "ballistic"
    assert P.parse("Активность пусковых⚠️", "TLK").type == "ballistic"
    from app.tracker import bal_oblasts
    assert "Харківська" in bal_oblasts("❗ Загроза балістики для низки східних та центральних регіонів")


def test_mig31_carrier_events():
    """Зліт МіГ-31К/І: окремий етап «носій у повітрі» для всієї України, свій відбій (скріни каналів 03.11)."""
    from app.tracker import mig_event
    for t in ["Зафіксовано зліт МіГ-31К! Підписатися | @svoiua", "Зліт МІГ 31-К‼️", "Зліт МіГ-31‼️ ‼️ ‼️",
              "В повітрі МіГ-31, Ймовірність застосування \"Кинджалів\"", "2х борти МіГ-31К у повітрі."]:
        assert mig_event(t) == "up", t
    for t in ["UPD 05:02: без фіксації Кинджалів, знову імітація.", "Відбій ракетної небезпеки по МІГ", "Посадка МіГ-31К"]:
        assert mig_event(t) == "down", t
    assert mig_event("Кинджал на Київ") is None and mig_event("МіГ-29 ЗСУ") is None


def test_alert_level_line_is_not_target_position():
    """03.11 CXID: «🟡 Харків та передмістя» — рівень тривоги, а шахед «перестрибнув» у центр Харкова."""
    o = P.parse("🟡 Харків та передмістя", "CX")
    assert o.no_target and o.type is None


def test_kharkiv_compound_names_and_city_context():
    """03.11: «Велику Данилівку» ≠ Велике (Житомирщина) + Данилівка (Крим); «над Харковом на П'ятихатки» —
    місто як контекст, не точка в центрі; «🟡 21:33, Харківський район» — рівень тривоги."""
    assert [r.place.name for r in P.parse("1 БпЛа невизначеного типу курсом на Велику Данилівку ⚠️", "M").places] == ["Велика Данилівка (Харків)"]
    assert [r.place.name for r in P.parse("Р. Шахед курсом на Малую Даниловку", "CX").places] == ["Мала Данилівка"]
    o = P.parse("⚠️ над Харковом на Пятихатки, Сокольники", "ND")
    assert "Харків" not in [r.place.name for r in o.places]
    assert P.parse("🟡 21:33, Харківський район", "CX").no_target
    assert [r.place.name for r in P.parse("Шахед на Нову Водолагу", "X").places] == ["Нова Водолага"]


def test_russian_forms_and_kharkiv_abbreviations():
    """03.11 журнал: рос. форми і місцеві скорочення харківських моніторів."""
    cases = {"Балаклею": "Балаклія", "Песочин": "Пісочин", "Сахновщину": "Сахновщина", "Большую Даниловку": "Велика Данилівка (Харків)",
             "Казачью Лопань": "Козача Лопань", "Каменную Яругу": "Кам’яна Яруга", "Ст Салтов": "Старий Салтів",
             "МД": "Мала Данилівка (Харків)", "БД": "Велика Данилівка (Харків)", "ВД": "Велика Данилівка (Харків)",
             "СС": "Північна Салтівка (Харків)", "Аэропорт": "Аеропорт (Харків)", "Комсомольское": "Слобожанське"}
    for w, want in cases.items():
        assert [r.place.name for r in P.parse("Шахед на " + w + " ⚠️", "TLK").places] == [want], w
    assert P.parse("Шахед на Харківщину", "X").places == []


def test_oblast_summary_list_is_positions_not_route():
    """03.11 Радар Харків: «11 Ударных БпЛА в области. Безлюдовка, Довжик, …» — де вони зараз, а не група ×11 з маршрутом."""
    segs = P.segments("11 Ударных БпЛА в области. Безлюдовка, Довжик, Первомайский, Дружба, Шевченково.")
    assert len(segs) == 5
    assert all(P.parse(s, "R").places[0].role == "p" for s in segs)


def test_short_reaktyv_is_jet():
    """03.11 (знайшов відбір для моделі): «1 реактив кружляє над Дніпром» (MK, SU, sumygo) не мав типу — 22 повідомлення."""
    assert P.parse("1 реактив кружляє над Дніпром.", "MK").type == "jet"
    assert P.parse("2 реактиви на Полтаву", "MK").type == "jet"


def test_llm_disabled_without_key(monkeypatch):
    """Без ANTHROPIC_API_KEY «другий парсер» вимкнено, сервер працює як раніше."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app.llm import LLM
    m = LLM()
    assert not m.on and m.stats()["mode"] == "off"
    assert LLM.suspicious(P, "1 реактив на Шпилівку", "SU") is None


def test_secrets_roundtrip_and_merge(tmp_path, monkeypatch):
    """Ключі через GitHub: шифр публічним ключем сервера → розшифрування лише сервером → злиття в .env (без втрати інших рядків)."""
    monkeypatch.setenv("ENV_KEY_FILE", str(tmp_path / "k.pem"))
    from app import secrets_sync as S
    blob = S.encrypt(S.public_pem(), "ANTHROPIC_API_KEY=test-a\ngroq=test-g\n# коментар\n")
    assert "test-a" not in blob
    new = S.parse_env(S.decrypt(blob))
    assert new == {"ANTHROPIC_API_KEY": "test-a", "GROQ_API_KEY": "test-g"}
    env = tmp_path / ".env"
    env.write_text("TG_SESSION=x\nANTHROPIC_API_KEY=old\n")
    ch = S.merge(env, new)
    txt = env.read_text()
    assert "TG_SESSION=x" in txt and "ANTHROPIC_API_KEY=test-a" in txt and "old" not in txt and "LLM_MODE=shadow" in txt
    assert set(ch) >= {"ANTHROPIC_API_KEY", "GROQ_API_KEY"}


def test_ai_consensus_and_ingest_validation():
    """Ансамбль моделей: місця й тип — більшістю; на мапу лише з перевіркою правилами й областю каналу."""
    import time
    from app.llm import consensus
    from app.ai_glue import AI
    c, agree = consensus([{"kind": "target", "type": "shahed", "now": ["Пісочин"], "to": ["Харків"]},
                          {"kind": "target", "type": "shahed", "now": ["Песочин"], "to": []},
                          {"kind": "target", "type": "jet", "now": [], "to": ["Харків"]}])
    assert c["type"] == "shahed" and c["now"] == ["Пісочин"] and c["to"] == ["Харків"] and agree == 0.67

    class L:  # заглушка моделі
        on_ai = on_merge = None
    tr = Tracker(SOURCES)
    ai = AI(L(), P, tr, lambda: {})
    now = time.time()
    good = {"src": "TLK", "t": now, "text": "Шахед Песочин → Харьков", "rules": [{"type": None, "places": []}],
            "llm": {"kind": "target", "type": "shahed", "now": ["Пісочин"], "to": ["Харків"]},
            "votes": {"a": {"type": "shahed"}, "b": {"type": "shahed"}}, "agree": 1.0}
    assert ai.ai_ingest(good) and any(t.ai for t in tr.tracks)
    far = dict(good, llm={"kind": "target", "type": "shahed", "now": [], "to": ["Одеса"]})
    assert not ai.ai_ingest(far)  # харківський канал, а місце в Одесі — відкидаємо
    split = dict(good, agree=0.5, votes={"a": {"type": "shahed"}, "b": {"type": "jet"}})
    assert not ai.ai_ingest(split)  # моделі не згодні — лише журнал


def test_live_diff_and_validation():
    """Живий ефір: різниця «що змінилось» з перевірених даних; дії моделі лише з наявними id."""
    import time
    from app import live
    tr = Tracker(SOURCES)
    now = time.time()
    o = P.parse("4 ударних БпЛА курсом на Шевченкове ⚠️", "M"); o.raw = "4 ударних БпЛА курсом на Шевченкове ⚠️"
    tr.ingest(o, "M", now - 60, None)
    st = tr.snapshot(now)
    d = live.diff(st, [], tr, now - 600, (36.25, 50.0), "Харківська")
    assert d["counts"]["new"] >= 1 and d["items"][0]["mentions"]
    steps = live.validate([{"say": "Ось — ціль", "action": "focus", "ids": ["НЕМАЄ-1"]},
                           {"say": "Нова", "action": "focus", "ids": [d["items"][0]["id"]]}], d)
    assert steps[0]["action"] is None and "—" not in steps[0]["say"] and steps[1]["action"] == "focus"
    assert live.fallback_script(d)[0]["say"].startswith("За ")


def test_stt_without_keys_returns_empty(monkeypatch):
    """Голос з iPhone: без ключів OpenAI/Groq розпізнавання чесно повертає порожньо (без помилки сервера)."""
    import asyncio
    for k in ("OPENAI_API_KEY", "GROQ_API_KEY", "GROK", "groq", "GROQ"):
        monkeypatch.delenv(k, raising=False)
    from app.llm import LLM
    assert asyncio.run(LLM().transcribe(b"x" * 5000, "audio/mp4")) == ("", None)


def test_radio_fallback_texts():
    """Радіо SKY без моделі: чесні короткі випуски з даних (свій регіон, сусіди, Україна)."""
    import asyncio, time
    from app import live
    tr = Tracker(SOURCES)
    o = P.parse("4 ударних БпЛА курсом на Шевченкове ⚠️", "M"); o.raw = "x"
    tr.ingest(o, "M", time.time() - 60, None)
    st = tr.snapshot(time.time())
    for sc in ("region", "neighbors", "country"):
        r = asyncio.run(live.radio(None, st, [], tr, time.time() - 600, (36.25, 50.0), "Харківська", sc))
        assert r["text"] and "—" not in r["text"] and r["scope"] == sc


def test_ukrainealarm_failover_parse():
    from app.alerts import OfficialAlerts
    tree = {"states": [{"regionId": "22", "regionType": "State", "regionName": "Харківська область", "regionChildIds": [
        {"regionId": "1293", "regionType": "District", "regionName": "Чугуївський район", "regionChildIds": [
            {"regionId": "1300", "regionType": "Community", "regionName": "Малинівська територіальна громада"}]},
        {"regionId": "1280", "regionType": "District", "regionName": "Харківський район", "regionChildIds": [
            {"regionId": "1281", "regionType": "Community", "regionName": "м. Харків та Харківська територіальна громада"}]}]},
        {"regionId": "9", "regionType": "State", "regionName": "Дніпропетровська область", "regionChildIds": []}]}
    par = OfficialAlerts._ua_tree(tree)
    assert par["1300"] == "Харківська" and par["9"] == "Дніпропетровська"
    data = [{"regionId": "9", "regionType": "State", "regionName": "Дніпропетровська область", "activeAlerts": [{"type": "AIR"}]},
            {"regionId": "1293", "regionType": "District", "regionName": "Чугуївський район", "activeAlerts": [{"type": "AIR"}]},
            {"regionId": "1281", "regionType": "Community", "regionName": "м. Харків та Харківська територіальна громада", "activeAlerts": [{"type": "AIR"}]},
            {"regionId": "1300", "regionType": "Community", "regionName": "Малинівська територіальна громада", "activeAlerts": [{"type": "ARTILLERY"}]}]
    a = OfficialAlerts()
    a.apply_ualarm(data, par)
    assert a.oblast_levels.get("Дніпропетровська") == 2
    assert "Чугуївський" in a.raion_levels
    assert any(p[2] == "м. Харків" for p in a.points)
    assert a.source.startswith("ukrainealarm")


def test_llm_breaker_and_tts_wav():
    import httpx
    from app.llm import LLM
    from app import tts
    l = LLM()
    req = httpx.Request("POST", "https://x")
    e = httpx.HTTPStatusError("x", request=req, response=httpx.Response(402, request=req, text="Payment Required"))
    l._fail("openrouter", e)
    assert not l._live("openrouter") and "402" in l.err_by["openrouter"]
    e2 = httpx.HTTPStatusError("x", request=req, response=httpx.Response(429, request=req, text="slow down"))
    l._fail("groq", e2)
    assert not l._live("groq") and l.off["groq"] - __import__("time").time() < 400
    w = tts._wav(b"\x00\x00" * 100, 24000)
    assert w[:4] == b"RIFF" and len(w) == 244


def test_say_form_and_radio_memory(monkeypatch):
    import asyncio
    from app.tts import say_form
    from app import live
    t = say_form("МіГ-31К зліт, Х-101 ×3, БпЛА")
    assert "міг тридцять один ка" in t and "ха сто один" in t and "безпілотник" in t and "×" not in t

    class L:
        on = True
        n = 0
        async def call(self, *a, **k):
            self.n += 1
            if self.n == 3:
                return {"action": "silence"}, "x:y"
            return {"action": "speak", "kind": "update", "display_text": "На Харківщині БпЛА у напрямку Пісочина.",
                    "speech_text": "На Харківщині безпілотник у напрямку Пісочина."}, "x:y"
    monkeypatch.setattr(live, "radio_context", lambda *a: ("ctx", "fb"))
    monkeypatch.setattr(live, "RADIO_MEM", {})
    m = L()
    r1 = asyncio.run(live.radio(m, {}, None, None, 0, None, "Харківська", "region", "s1"))
    r2 = asyncio.run(live.radio(m, {}, None, None, 0, None, "Харківська", "region", "s1"))
    r3 = asyncio.run(live.radio(m, {}, None, None, 0, None, "Харківська", "region", "s1"))
    r4 = asyncio.run(live.radio(m, {}, None, None, 0, None, "Харківська", "region", "s2"))  # новий слухач: своє зведення
    assert r1["text"] and "безпілотник" in r1["speech"] and r2["text"] == "" and r3.get("quiet") and r4["text"]
    out = asyncio.run(live.radio(None, {"health": {"telegram": False, "alerts": True}}, None, None, 0, None, "Харківська", "region", "s3"))
    assert out["kind"] == "outage" and "недоступні" in out["text"]


def test_scrub_track_ids():
    from app.live import scrub
    t = scrub("Ш-1023 курсом на Чугуїв, Х-101 і КН-23 (РБ-12).", {"Ш-1023": "шахед"})
    assert "Ш-1023" not in t and "РБ-12" not in t and "Х-101" in t and "КН-23" in t and t.startswith("шахед")


def test_vote_cheap_first_and_cache():
    import asyncio
    from app import llm as L
    m = L.LLM()
    m.cli = object()
    m.others = [("openai", "k", "", "gpt-4o-mini"), ("groq", "k", "", "gpt-oss"), ("mistral", "k", "", "small")]
    m.key = ""
    calls = []

    async def one(cli, prov, *a, **k):
        calls.append(prov[0])
        return {"kind": "target", "type": "shahed", "to": ["Чугуїв"]}
    m._one = one
    v = asyncio.run(m.vote("S", "текст", {"name": "x"}))
    assert set(calls) == {"groq", "mistral"} and len(v) == 2  # дешеві згодні — платну не питали
    asyncio.run(m.vote("S", "текст", {"name": "x"}))
    assert len(calls) == 2  # повтор того самого тексту — з кешу


def test_ecopark_lysa_hora_and_far_alternative():
    from app.parser import Parser
    from app.tracker import Tracker
    p = Parser()
    o = p.parse("1 ударний БпЛА рухається над Екопарком, курсом на Лісне", "KM")
    assert all(abs(r.place.lat - 50.114) < 0.05 for r in o.places)  # Лісне під Харковом, не біля Зміїва
    o = p.parse("2х БпЛА курсом на Лису Гору (Миколаївщина)", "D")
    assert o.places[0].place.lat < 49 and "Харків" not in o.places[0].place.name
    tr = Tracker(SOURCES)
    t0 = 1_800_000_000
    tr.ingest(p.parse("Шахед над Лісним", "D"), "D", t0)
    tr.ingest(p.parse("1 ударний БпЛа курсом на Лозова/Питомник", "M"), "M", t0 + 60)
    act = [x for x in tr.snapshot(t0 + 90)["tracks"] if x["status"] == "active" and x["type"] == "shahed"]
    assert act and all(x.get("next") != "Лозова" for x in act) and act[0]["lat"] > 49.9  # не «летить» через центр Харкова на Лозову


def test_public_endpoints_hide_internals_and_rate_limit():
    from fastapi.testclient import TestClient
    from app import main as M
    c = TestClient(M.app)
    r = c.get("/api/llm").json()
    assert set(r) <= {"enabled", "assist"}  # без провайдерів і тексту помилок
    assert c.get("/api/llm/check").status_code == 403
    h = c.get("/api/llm").headers
    assert h.get("x-content-type-options") == "nosniff" and h.get("cache-control") == "no-store"
    M._hits.clear()
    codes = [c.get("/api/ask?obl=").status_code for _ in range(10)]
    assert 429 in codes
