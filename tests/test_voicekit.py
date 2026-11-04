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
    fr = v.compose(f)
    assert fr[:4] == ["Увага!", "Три шахеди", "на півночі,", "за двадцять п'ять кілометрів від вас."]
    voc = set(v.vocabulary())
    # усе, крім назв місць, — із заготовленого словника (звучить без синтезу)
    assert all(x in voc for x in fr if not x.startswith(("Місце:", "Курс:")))
    assert v.compose({"bal": [], "near": [], "n_near": 0, "alert": False})[-1] == "Повідомлень про цілі поруч немає."


def test_alert_frags_and_budget():
    fr = v.alert_frags("Шахед ×2, курс на ваш район. 24 км з півдня, ~8 хв")
    assert fr == ["Шахед.", "Дві цілі.", "Курс на ваш район.", "Двадцять п'ять кілометрів з півдня.", "Приблизно вісім хвилин."]
    assert v.alert_frags("🔴 Повітряна тривога: Харківська обл.") == ["Повітряна тривога.", "Харківська область."]
    # разове озвучення словника радіо — у межах ~12 тис. символів (≈$0,10–0,15)
    assert sum(len(x) for x in v.vocabulary()) < 12000


def test_oblast_country_compose():
    o = v.compose_oblast({"obl": "Запорізька", "whole": True, "al_raions": [], "groups": {}})
    assert o == ["Запоріжжя.", "Повітряна тривога на всю область.", "Повідомлень про цілі в області немає."]
    c = v.compose_country({"al": ["a", "b"], "bal": [], "top": [("Харківська", [("shahed", 5)])]})
    assert c == ["Огляд по Україні.", "Областей з тривогою: дві.", "Найбільше повідомлень про цілі:", "Харківщина,", "переважно шахеди."]


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
    assert v.compose_changes(f, prev) == ["Україна, зміни.", "Нові тривоги:", "Сумщина."]
    assert v.compose_changes(dict(f, al=["Харківська"]), prev) == []


def test_far_target_when_nothing_near():
    fr = v.compose({"bal": [], "near": [], "n_near": 0, "alert": True, "raion_alert": False, "radius": 25,
                    "far": {"type": "shahed", "n": 2, "km": 63, "side": "на сході", "at": "Чугуїв", "appr": True}})
    assert fr == ["Тривога в області триває.", "У радіусі двадцяти п'яти кілометрів повідомлень про цілі немає.", "Найближча ціль:",
                  "Два шахеди", "на сході,", "за шістдесят п'ять кілометрів від вас.", "Місце: Чугуїв.", "Рухається у ваш бік."]
