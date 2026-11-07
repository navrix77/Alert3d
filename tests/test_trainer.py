import json
from app import trainer


def test_params_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(trainer, "PARAMS", tmp_path / "params.json")
    assert trainer.load_params() == {}
    (tmp_path / "params.json").write_text(json.dumps({"speed_over": {"shahed": 170}}))
    assert trainer.load_params()["speed_over"]["shahed"] == 170


def test_score_weighted():
    rep = {"shahed": {"route": {"10": {"med": 2.0, "n": 10}, "30": {"med": 4.0, "n": 30}}}}
    assert trainer._score(rep, "shahed") == (3.5, 40)
    assert trainer._score(rep, "x")[1] == 0
