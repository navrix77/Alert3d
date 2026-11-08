import json
from app import dictlearn, parser as P


def _rows(w, n=2, src="M"):
    return [{"kind": "no_place", "src": src, "place": w, "text": f"пост {i} {w}", "t": i} for i in range(n)]


def test_candidates_need_two_posts_and_city_region():
    assert dictlearn.candidates(_rows("Дафі", 1)) == []
    c = dictlearn.candidates(_rows("Дафі", 2))
    assert c and c[0][0] == "Дафі" and c[0][1] == "Харківська"


def test_run_adds_and_hot_loads(tmp_path, monkeypatch):
    monkeypatch.setattr(dictlearn, "LEARNED", tmp_path / "l.json")
    monkeypatch.setattr(dictlearn, "NEG", tmp_path / "n.json")
    out = dictlearn.run(_rows("Карпатська", 3), geo=lambda w, c, la, lo, r: ("Карпатська вулиця", 50.01, 36.30), sleep=0)
    assert out["added"] == ["Карпатська вулиця (Харків)"]
    n = P.reload_learned()
    assert n >= 1
    o = P.Parser().parse("шахед на Карпатську", "M")
    assert any("Карпатська" in r.place.name for r in o.places), o.places
    monkeypatch.setattr(dictlearn, "LEARNED", tmp_path / "gone.json")
    P.reload_learned()


def test_negative_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(dictlearn, "LEARNED", tmp_path / "l.json")
    monkeypatch.setattr(dictlearn, "NEG", tmp_path / "n.json")
    calls = []
    g = lambda *a: calls.append(1)  # noqa: E731
    dictlearn.run(_rows("Невідомка", 3), geo=g, sleep=0)
    dictlearn.run(_rows("Невідомка", 3), geo=g, sleep=0)
    assert len(calls) == 1
