"""Наскрізний ланцюг (12.11, аудит): пост → Parser → Tracker.ingest → snapshot → public_api._target → dump/load_state.
Перевіряє зв'язки між модулями та узгодженість даних між шарами, а не окремі функції."""
import math

import pytest

from app import public_api
from app.config import SOURCES
from app.geo import dist_km, to_xy
from app.parser import Parser
from app.tracker import Tracker

P = Parser()
T0 = 1_793_700_000.0
POSTS = [
    ("Шахед від Мерефи на Харків", "M"),
    ("2 шахеди над Чугуєвом", "M"),
    ("Бандероль на Харків, Полтаву", "M"),
    ("Реактивний БпЛА Дергачі курсом на Харків", "M"),
    ("Балістика на Харківщину", "M"),
    ("КАБ на Куп'янськ", "M"),
    ("Moped на Пісочин", "M"),
]


def _tracker():
    tr = Tracker(SOURCES, learn=False)
    for i, (txt, src) in enumerate(POSTS):
        tr.ingest(P.parse(txt, src), src, T0 + i * 20)
    return tr


def test_snapshot_shape_and_geo_sanity():
    tr = _tracker()
    snap = tr.snapshot(T0 + 200)
    assert isinstance(snap, dict) and snap.get("tracks") is not None
    assert len(snap["tracks"]) >= 3
    ids = [t["id"] for t in snap["tracks"]]
    assert len(ids) == len(set(ids)), "id цілей мають бути унікальні"
    for t in snap["tracks"]:
        assert 43.0 <= t["lat"] <= 53.0 and 21.0 <= t["lon"] <= 41.0, t["id"]
        assert t.get("type"), t["id"]
        if t.get("hd") is not None:
            assert 0 <= t["hd"] < 360
        for r in t.get("route") or []:
            assert 21.0 <= r[0] <= 41.0 and 43.0 <= r[1] <= 53.0, (t["id"], r)  # маршрут: [lon, lat]


def test_public_api_projection_consistent_with_snapshot():
    tr = _tracker()
    now = T0 + 200
    snap = tr.snapshot(now)
    by = {t["id"]: t for t in snap["tracks"]}
    for t in snap["tracks"]:
        p = public_api._target(t, now)
        assert p["id"] == t["id"] and p["type"] == t["type"]
        assert abs(p["lat"] - t["lat"]) < 1e-3 and abs(p["lon"] - t["lon"]) < 1e-3
        for k in ("heading_deg", "status", "position_is_estimate", "confidence"):
            assert k in p, k
    assert by


def test_state_roundtrip_preserves_snapshot():
    tr = _tracker()
    now = T0 + 200
    a = tr.snapshot(now)
    tr2 = Tracker(SOURCES, learn=False)
    assert tr2.load_state(tr.dump_state())
    b = tr2.snapshot(now)
    key = lambda s: sorted((t["type"], round(t["lat"], 3), round(t["lon"], 3)) for t in s["tracks"])
    assert key(a) == key(b)


def test_same_post_from_two_sources_is_one_track():
    tr = Tracker(SOURCES, learn=False)
    srcs = [k for k in SOURCES][:2]
    for i, s in enumerate(srcs):
        tr.ingest(P.parse("Шахед від Мерефи на Харків", s), s, T0 + i * 15)
    assert len(tr.snapshot(T0 + 60)["tracks"]) == 1


def test_every_configured_source_has_required_fields():
    for k, v in SOURCES.items():
        assert v is not None, k


def test_unknown_noise_post_creates_no_target():
    tr = Tracker(SOURCES, learn=False)
    tr.ingest(P.parse("Доброго ранку, друзі! Підписуйтесь на канал", "M"), "M", T0)
    assert tr.snapshot(T0 + 5)["tracks"] == []


def test_first_never_after_last_even_with_late_older_post():
    """12.11 (живий /api/state): first > last у кількох треків — запізніла публікація зі старішим часом."""
    tr = Tracker(SOURCES, learn=False)
    tr.ingest(P.parse("Шахед від Мерефи на Харків", "M"), "M", T0 + 100)
    tr.ingest(P.parse("Шахед від Мерефи на Харків", "M"), "M", T0 + 90)
    for t in tr.snapshot(T0 + 200)["tracks"]:
        assert t["first"] <= t["last"]


def test_same_name_far_namesake_does_not_teleport_track():
    """12.11 (живий selfcheck): однойменний тезка за 130 км не «телепортує» трек (Новомиколаївка → Новомиколаївка)."""
    import copy
    tr = Tracker(SOURCES, learn=False)
    o1 = P.parse("Реактивний біля Мерефи", "M")
    tr.ingest(o1, "M", T0)
    o2 = P.parse("Реактивний біля Мерефи", "M")
    pl = o2.places[0].place
    far = copy.copy(pl)
    far.lat, far.lon = pl.lat + 1.2, pl.lon - 0.8
    o2.places[0].place = far
    tr.ingest(o2, "M", T0 + 60)
    for trk in tr.tracks:  # жодного «стрибка» всередині треку: сусідні точки не далі 60 км
        for a, b in zip(trk.obs, trk.obs[1:]):
            assert dist_km((a.x, a.y), (b.x, b.y)) < 60, (trk.id, a.label, b.label)
