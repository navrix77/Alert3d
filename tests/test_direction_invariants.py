"""Інваріанти напрямку для Харківщини (11.11, власник): цілі (шахед/БпЛА/«Молнія»/реактивний/«Бандероль») летять З боку
кордону й окупованих територій В місто. Ціль, названа біля міста, показується в місті й ніколи не веде за нього
чи назад до РФ: курс (hd) не вказує в бік фронту, маршрут не веде до кордону, позиція на мапі не «пролітає» названий пункт.
Плюс «Бандероль»: групи на різні пункти призначення (Полтава ≠ Харківщина) — окремі треки, пункт призначення — не місце пуску."""
import pytest

from app.config import SOURCES
from app.geo import ang_diff, dist_km, to_xy
from app.parser import Parser
from app.tracker import Tracker

P = Parser()
T0 = 1_793_700_000.0
WORD = {"shahed": "Шахед", "uav": "БпЛА", "molniya": "Молнія", "jet": "Реактивний БпЛА", "banderol": "Бандероль"}
TYPES = tuple(WORD)
# (називний, родовий, орудний, знахідний) + координати міста
CITY = {"Харків": ("Харків", "Харкова", "Харковом", "Харків", (49.9935, 36.2304)),
        "Чугуїв": ("Чугуїв", "Чугуєва", "Чугуєвом", "Чугуїв", (49.835, 36.688)),
        "Богодухів": ("Богодухів", "Богодухова", "Богодуховом", "Богодухів", (50.16, 35.52)),
        "Ізюм": ("Ізюм", "Ізюма", "Ізюмом", "Ізюм", (49.21, 37.26))}
START = ["Мерефа", "Пісочин", "Люботин", "Південне", "Дергачі", "Чугуїв", "Богодухів", "Печеніги", "Козача Лопань", "Балаклія"]
DEST = ["Харків", "Чугуїв", "Богодухів", "Люботин"]
DTS = (0, 120, 300, 600, 900)


def _run(text, src="M", t=0):
    tr = Tracker(SOURCES, learn=False)
    tr.ingest(P.parse(text, src), src, T0 + t)
    return tr


def _front(pos):
    return Tracker._front_dist(pos), Tracker._front_bearing(pos)


def _check_dir(x):
    """hd не вказує в бік фронту; маршрут не веде ближче до кордону (там, де лінія далеко від міста ≥15 км)."""
    pos = to_xy(x["lat"], x["lon"])
    fd, fb = _front(pos)
    if x["hd"] is not None and fb is not None and 15 <= fd <= 120:
        assert ang_diff(x["hd"], fb) <= 120, (x["id"], x["hd"], fb)
    if 15 <= fd <= 120:
        for r in x["route"]:
            assert Tracker._front_dist(to_xy(r[0], r[1])) >= fd - 3, (x["id"], r)


@pytest.mark.parametrize("typ", TYPES)
def test_course_to_city_never_points_to_front_nor_past_city(typ):
    """«X біля A курсом на B»: курс не в бік кордону, маршрут не до кордону, мітка не проходить повз названий пункт."""
    for a in START:
        for b in DEST:
            if a == b:
                continue
            text = f"{WORD[typ]} у районі {a} курсом на {b}"
            tr = _run(text)
            trk = tr.tracks[0]
            for dt in DTS:
                for x in tr.snapshot(T0 + dt)["tracks"]:
                    if x["status"] != "active":
                        continue
                    _check_dir(x)
                    if trk.route:
                        dest, st, pos = trk.route[-1].xy, (trk.obs[0].x, trk.obs[0].y), to_xy(x["lat"], x["lon"])
                        if _front(st)[0] < 15:
                            continue
                        beyond = (pos[0] - dest[0]) * (dest[0] - st[0]) + (pos[1] - dest[1]) * (dest[1] - st[1]) > 0
                        assert not (beyond and dist_km(pos, dest) > 2.5), (text, dt, dist_km(pos, dest))


@pytest.mark.parametrize("typ", TYPES)
def test_target_named_near_city_is_shown_in_city(typ):
    """Ціль, названа над/біля/в районі міста або «на місто» (без позиції), стоїть у місті, а не виходить із нього."""
    for name, (n, g, i, a, cxy) in CITY.items():
        c = to_xy(*cxy)
        for text in (f"{WORD[typ]} над {i}", f"{WORD[typ]} біля {g}", f"{WORD[typ]} в районі {g}",
                     f"{WORD[typ]} на {a}", f"{WORD[typ]} курсом на {a}"):
            tr = _run(text)
            for dt in DTS:
                for x in tr.snapshot(T0 + dt)["tracks"]:
                    if x["status"] != "active":
                        continue
                    assert dist_km(to_xy(x["lat"], x["lon"]), c) <= 8.5, (text, dt, x["lat"], x["lon"])
                    _check_dir(x)


@pytest.mark.parametrize("typ", TYPES)
def test_from_border_to_city_not_back(typ):
    """«з Бєлгорода на Харків» / «від Козачої Лопані до Харкова»: ціль у Харкові, курс — від кордону (не на північ)."""
    for text in (f"{WORD[typ]} з Бєлгорода на Харків", f"{WORD[typ]} Козача Лопань на Харків"):
        tr = _run(text)
        for dt in (0, 120, 300):
            for x in tr.snapshot(T0 + dt)["tracks"]:
                if x["status"] == "active":
                    _check_dir(x)
                    assert x["lat"] < 50.4  # не на кордоні й не за ним


def test_merefa_to_kharkiv_course_does_not_lead_to_front():
    """Баг 11.11: шахед біля Мерефи «курсом на Харків» мав hd 38° (на північ, до кордону): курс до пункту ближчого до фронту
    не береться в напрямок — носом від лінії фронту."""
    tr = _run("Шахед у районі Мерефи курсом на Харків")
    x = tr.snapshot(T0 + 60)["tracks"][0]
    pos = to_xy(x["lat"], x["lon"])
    assert ang_diff(x["hd"], Tracker._front_bearing(pos)) <= 120


def test_jet_course_to_city_stops_in_city():
    """Баг 11.11: реактивний «Дергачі → Харків» через 5 хв був за містом (на 4,5 км далі), через 10 хв — на 27 км."""
    tr = _run("Реактивний БпЛА у районі Дергачів курсом на Харків")
    c = to_xy(49.9935, 36.2304)
    for dt in (300, 600):
        x = tr.snapshot(T0 + dt)["tracks"][0]
        assert dist_km(to_xy(x["lat"], x["lon"]), c) < 6


# ---------------------------------------------------------------- «Бандероль»: окремі пункти призначення
def _snap(texts):
    tr = Tracker(SOURCES, learn=False)
    for txt, dt, src in texts:
        tr.ingest(P.parse(txt, src), src, T0 + dt)
    return tr, tr.snapshot(T0 + texts[-1][1] + 1)["tracks"]


def test_banderol_poltava_separate_from_kharkiv():
    tr, out = _snap([("Бандероль на Полтаву", 0, "M"), ("Бандероль на Харків", 30, "N")])
    assert sorted(x["next"] for x in out) == ["Полтава", "Харків"]


def test_banderol_list_of_far_destinations_splits_into_tracks():
    """«Бандероль на Харків, Полтаву» — дві групи, а не один трек з маршрутом через обидва міста."""
    for text in ("Бандероль на Харків, Полтаву", "2 Бандеролі на Харків та Полтаву"):
        tr, out = _snap([(text, 0, "M")])
        assert len(out) == 2 and sorted(x["next"] for x in out) == ["Полтава", "Харків"], text
        assert all(len(x["route_names"]) <= 1 for x in out)


def test_banderol_kharkiv_region_destinations_stay_one_group():
    """Харків і Чугуїв (30 км) — один напрямок, групу не дробимо."""
    tr, out = _snap([("Бандероль на Харків, Чугуїв", 0, "M")])
    assert len(out) == 1


def test_banderol_not_merged_by_dedup_across_destinations():
    """Бандероль біля Мерефи (курс на Полтаву) і «курсом на Харків» — різні групи, дедуплікація їх не зливає."""
    tr, out = _snap([("Бандероль в районі Мерефи курсом на Полтаву", 0, "M"), ("Бандероль курсом на Харків", 20, "N")])
    assert len(out) == 2 and not [t for t in tr.tracks if t.merged]


def test_banderol_same_destination_from_two_channels_is_one_track():
    tr, out = _snap([("Бандероль на Полтаву", 0, "M"), ("Бандероль курсом на Полтаву", 20, "N")])
    assert len(out) == 1


def test_banderol_destination_is_not_shown_as_launch_place():
    """«Звідки летить»: пункт призначення (єдине, що назвали) не показується як місце першої появи/пуску, пуск від нього не оцінюється."""
    tr, out = _snap([("Бандероль на Полтаву", 0, "M")])
    x = out[0]
    assert x["launch"] is None
    assert "не місце пуску" in x["entry"][2]
    # а канал з позицією лишає звичайний підпис
    tr, out = _snap([("Бандероль в районі Мерефи курсом на Полтаву", 0, "M")])
    assert out[0]["entry"][2] == "Мерефа"


def test_front_bearing_vovchansk_kupiansk_inland():
    """Вовчанськ/Куп'янськ: курс від фронту вглиб (на південь/захід), а не на схід."""
    from app.tracker import Tracker, _gxy
    for la, lo in ((50.29, 36.94), (49.71, 37.62)):
        b = Tracker._front_bearing(_gxy(la, lo))
        assert b is not None and 150 <= b <= 290
