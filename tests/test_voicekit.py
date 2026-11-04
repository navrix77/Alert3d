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
    assert v.compose({"bal": [], "near": [], "n_near": 0, "alert": False})[-1] == "Поруч з вами цілей немає."


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
