"""Голосові заготовки Sky Radio: граматика числівників і склад повідомлення."""
from app import voicekit as v


def test_numbers_agree():
    assert v.count_type(1, "shahed") == "Шахед"
    assert v.count_type(2, "cruise") == "Дві крилаті ракети"
    assert v.count_type(5, "shahed") == "П'ять шахедів"
    assert v.count_type(21, "cruise") == "Двадцять одна крилата ракета"
    assert v.count_type(12, "jet") == "Дванадцять реактивних безпілотників"
    assert v.side_dist("на сході", 22) == "на сході, за двадцять кілометрів від вас."
    assert v.side_dist("на сході", 3) == "на сході, за три кілометри від вас."
    assert v.eta(1) == "Орієнтовно одна хвилина."


def test_compose_and_vocab():
    f = {"bal": [], "near": [{"type": "shahed", "word": "3 шахеди", "km": 23, "side": "на півночі", "appr": True, "eta": 8,
                              "next": None, "at": "Чугуїв", "named_km": 27}], "n_near": 1, "urgent": True, "alert": True, "raion_alert": False}
    fr = v.compose(f)
    assert fr[:3] == ["Увага!", "Три шахеди", "на півночі, за двадцять п'ять кілометрів від вас."]
    voc = set(v.vocabulary())
    # усе, крім назв місць, — із заготовленого словника (звучить без синтезу)
    assert all(x in voc for x in fr if not x.startswith(("Місце:", "Курс:")))
    assert v.compose({"bal": [], "near": [], "n_near": 0, "alert": False})[-1] == "Поруч з вами цілей немає."
