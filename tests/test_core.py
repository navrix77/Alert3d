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
    assert abs(moved - 170 * MAP_K["shahed"] * 10 / 60) < 2 and s["vmap"] == round(170 * MAP_K["shahed"]) and s["hd_src"] == "learned"
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
    assert len(sent) == 1 and sent[0]["title"].startswith("20 цілей")  # одне зведене, а не 20 сповіщень
    sent.clear()
    import time as _t
    for k in pu.armed["ExponentPushToken[abcdefghijkl]"]:
        pu.armed["ExponentPushToken[abcdefghijkl]"][k] = _t.time() - 300
    asyncio.run(pu.tick(Cli(), {"tracks": [dict(t, status="lost") for t in many]}))
    assert len(sent) == 1 and "минула" in sent[0]["title"]
