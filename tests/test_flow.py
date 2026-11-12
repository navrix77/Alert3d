"""FLOW (тіньовий трекер ланцюгів): димові перевірки. Якість міряє scripts/flow_lab.py на реальному журналі."""
from app.flow import FlowTracker
from app.geo import dist_km, to_xy
from app.parser import Parser
from app.tracker import Tracker

P = Parser()
T0 = 1_793_700_000.0


def _ft(posts):
    ft = FlowTracker(front_bearing=Tracker._front_bearing)
    for txt, dt in posts:
        ft.ingest(P.parse(txt, "K"), "K", T0 + dt)
    return ft


def test_chain_moves_from_origin_to_destination_and_keeps_one_chain():
    ft = _ft([("Реактивний БпЛА від Ізюма курсом на Барвінкове", 0), ("Реактивний БпЛА курсом на Барвінкове", 40)])
    assert len(ft.chains) == 1
    c = ft.chains[0]
    iz, ba = to_xy(49.21, 37.26), to_xy(48.90, 37.02)
    assert dist_km(ft.pos(c, T0), iz) < 8
    assert dist_km(ft.pos(c, T0 + 600), ba) < 25  # дійшов і не полетів далеко за названий пункт
    assert dist_km(ft.pos(c, T0 + 120), iz) > 5   # рухається, а не стоїть


def test_far_target_is_separate_chain_and_close_ends_it():
    ft = _ft([("Шахед над Мерефою", 0), ("Шахед над Ніжином", 30)])
    assert len(ft.chains) == 2
    ft.ingest(P.parse("Шахед над Мерефою більше не фіксується", "K"), "K", T0 + 90)
    assert sum(1 for c, _ in ft.shown(T0 + 100)) <= 1
