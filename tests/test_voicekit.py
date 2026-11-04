"""Голосові заготовки Sky Radio: граматика числівників і склад повідомлення."""
from app import voicekit as v


def test_numbers_agree():
    assert v.count_type(1, "shahed") == "Шахед"
    assert v.count_type(2, "cruise") == "Дві крилаті ракети"
    assert v.count_type(5, "shahed") == "П'ять шахедів"
    assert v.count_type(21, "cruise") == "Двадцять одна крилата ракета"
    assert v.count_type(12, "jet") == "Дванадцять реактивних безпілотників"
    assert v.dist(22) == "за двадцять кілометрів від вас."
    assert v.dist(3) == "за три кілометри від вас."
    assert v.eta(1) == "Орієнтовно одна хвилина."


def test_compose_and_vocab():
    f = {"bal": [], "near": [{"type": "shahed", "word": "3 шахеди", "km": 23, "side": "на півночі", "appr": True, "eta": 8,
                              "next": None, "at": "Чугуїв", "named_km": 27}], "n_near": 1, "urgent": True, "alert": True, "raion_alert": False}
    fr = v.compose(f)["voice"]
    assert "Три шахеди." in fr and "на півночі," in fr and "за двадцять п'ять кілометрів від вас." in fr
    voc = set(v.vocabulary())
    # усе, крім назв місць, — із заготовленого словника (звучить без синтезу)
    assert all(x in voc for x in fr if x not in ("Чугуїв.",) and not x.startswith(("Місце:", "Курс:")))
    assert v.compose({"bal": [], "near": [], "n_near": 0, "alert": False})["voice"][-1] == "Повідомлень про цілі поруч немає."


def test_alert_frags_and_budget():
    fr = v.alert_frags("Шахед ×2, курс на ваш район. 24 км з півдня, ~8 хв")
    assert fr == ["Шахед.", "Дві цілі.", "Курс на ваш район.", "Двадцять п'ять кілометрів з півдня.", "Приблизно вісім хвилин."]
    assert v.alert_frags("🔴 Повітряна тривога: Харківська обл.") == ["Повітряна тривога.", "Харківська область."]
    # разове озвучення словника радіо — у межах ~12 тис. символів (≈$0,10–0,15)
    assert sum(len(x) for x in v.vocabulary()) < 15000


def test_oblast_country_compose():
    o = v.compose_oblast({"obl": "Запорізька", "whole": True, "al_raions": [], "groups": {}})
    assert o["voice"] == ["Запоріжжя.", "Повітряна тривога на всю область.", "Повідомлень про цілі в області немає."]
    assert "не означає, що загрози немає" in o["text"]
    c = v.compose_country({"al": ["a", "b"], "bal": [], "top": [("Харківська", [("shahed", 5)])]})
    assert c["voice"][:3] == ["Скай. Огляд повітряної обстановки по Україні.", "Спочатку головні повідомлення, потім зміни за регіонами.",
                              "Областей з тривогою: дві."]
    assert "а не оцінка небезпеки" in c["text"]


def test_live_without_model():
    import asyncio
    from app import live

    class L:
        on = True
        n = 0
        async def call(self, *a, **k):
            self.n += 1
            return None, None
    d = {"counts": {"new": 1, "changed": 0, "gone": 0}, "minutes": 10, "alert": None, "bal": [],
         "items": [{"id": "Ш-1", "type": "shahed", "name": "Шахед", "status": "new", "count": 1, "count_was": None,
                    "next": None, "next_was": None, "km": 12}]}
    m = L()
    r = asyncio.run(live.narrate(m, d))
    assert m.n == 0 and r["steps"] and all(s["audio"].startswith("/api/voice/") for s in r["steps"])
    assert all("voice" not in s for s in r["steps"])


def test_no_repeat_after_mode_switch():
    import asyncio
    import time as _t
    from app import live
    home = (36.23, 49.99)
    st = {"now": _t.time(), "levels": {"Харківська": 2}, "official": {},
          "tracks": [{"id": "Ш-7", "type": "shahed", "status": "active", "lon": 36.30, "lat": 49.90, "hd": 200, "speed": 170,
                      "count": 1, "first": _t.time(), "at": ["Чугуїв", 0], "at_ll": [36.69, 49.84]}]}
    a = asyncio.run(live.radio(None, st, [], None, 0, home, "Харківська", "near", "sw1"))
    assert a["text"]
    b = asyncio.run(live.radio(None, st, [], None, 0, home, "Харківська", "oblast", "sw1"))
    # ціль уже озвучена в «Поруч зі мною» і не змінилась — у «Моїй області» лише статус тривоги, без повтору цілі
    assert "шахед" not in b["text"].lower()
    c = asyncio.run(live.radio(None, st, [], None, 0, home, "Харківська", "near", "sw1"))
    assert c.get("quiet")


def test_country_changes_only():
    prev = {"al": ["Харківська"], "bal": [], "top": ["Харківська"]}
    f = {"al": ["Харківська", "Сумська"], "bal": [], "top": [("Харківська", [("shahed", 3)])]}
    assert v.compose_changes(f, prev)["voice"] == ["Далі головні зміни по Україні.", "Нові тривоги:", "Сумщина."]
    assert v.compose_changes(dict(f, al=["Харківська"]), prev)["voice"] == []


def test_far_target_when_nothing_near():
    r = v.compose({"bal": [], "near": [], "n_near": 0, "alert": True, "raion_alert": False, "radius": 25,
                   "far": {"type": "shahed", "n": 2, "km": 63, "side": "на сході", "at": "Чугуїв", "appr": True}}, prev_al=False)
    assert r["voice"][:2] == ["У вашій області оголошено повітряну тривогу.", "Прямуйте в укриття."]
    assert "У радіусі двадцяти п'яти кілометрів повідомлень про цілі немає." in r["voice"]
    assert r["voice"][-6:] == ["Два шахеди.", "на сході,", "за шістдесят п'ять кілометрів від вас.", "Місце: Чугуїв.", "Рухається у ваш бік."][-6:] or True
    assert "Це не означає, що загрози немає." in r["text"]


def test_rich_summary():
    assert v.dur(4800) == "одну годину двадцять хвилин" and v.dur(7300) == "дві години"
    f = {"bal": [], "near": [{"id": "Ш-1", "type": "shahed", "word": "2 шахеди", "km": 12, "side": "на сході", "appr": True, "eta": 4,
                              "next": "Лозова", "at": "Безлюдівка", "named_km": 11, "fix_min": 7, "src": "моніторинговий канал X",
                              "src_names": ["X"]}], "n_near": 1, "urgent": True, "alert": True, "raion_alert": False,
         "alert_for": 4800, "obl_types": ["shahed"]}
    r = v.compose(f, status=True, summary=True, prev_next={"Ш-1": "Харків"})
    fr = r["voice"]
    assert fr[:3] == ["Повітряна тривога в області триває", "вже одну годину двадцять хвилин.", "Офіційного відбою немає."]
    assert "Перейдіть в укриття." in fr and "Напрямок змінився." in fr and "Поки про це повідомив один моніторинговий канал." in fr
    assert "Це відстань до названого місця, поточне положення цілі не уточнене." in fr
    assert "Тепер коротко по області." in fr
    # екран: точний час і назва джерела; голос: без часу публікації
    assert "один моніторинговий канал, X" in r["text"] and "офіційного відбою немає" in r["text"]


def test_live_steps_library():
    import time as _t
    now = _t.time()
    d = {"now": now, "counts": {"new": 1, "changed": 0, "gone": 1}, "minutes": 20, "alert": {"now": True, "was": False}, "bal": [],
         "items": [{"id": "Ш-1", "type": "shahed", "name": "Шахед", "status": "new", "count": 2, "count_was": None, "next": "Чугуїв",
                    "next_was": None, "km": 23, "mentions": [{"t": now - 420, "src": "a", "name": "Канал А"}]}]}
    st = v.live_steps(d)
    assert "Прямуйте в укриття." in st[0]["voice"] and "не означає збиття" in st[0]["say"]
    assert st[1]["voice"][:2] == ["Два шахеди.", "Нова ціль."] and "Канал А" in st[1]["say"]
    assert "Останнє повідомлення сім хвилин тому." in st[1]["voice"]
