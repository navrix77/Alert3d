"""Звідки пускають (07.11, власник: «вивчи, звідки і як пускають»). Довідник зон пуску за типом цілі: курс без підказки каналів
береться від найближчої зони пуску, що досяжна за дальністю типу. Джерела: відкриті (lb.ua «Полювання на Бандеролі», ГУР, Повітряні сили).
Бандероль — ракета повітряного пуску (з БпЛА «Оріон», дальність до ~500 км, ~500 км/год; наземний пуск лише заявляли
росіяни): тому для неї курс беремо від найближчої ділянки лінії фронту/кордону (tracker), зони нижче — запасний варіант
для цілей далеко від фронту. Координати наближені; це лише запасний напрямок, названий каналами курс завжди важливіший."""
from __future__ import annotations

# (lat, lon, назва)
CRIMEA = [(45.9, 34.8, "Арабатська стрілка"), (45.1, 33.6, "Саки/Бельбек"), (45.3, 36.5, "Керченський напрямок")]
BELGOROD_KURSK_BRYANSK = [(50.6, 36.6, "Білгородська обл."), (51.7, 36.2, "Курська обл."), (53.2, 34.4, "Брянська обл.")]
AZOV = [(46.9, 36.0, "Азовське узбережжя"), (47.6, 39.9, "Зерноград/Коренівськ")]
VORONEZH = [(51.7, 39.2, "Воронезька обл.")]
BLACK_SEA = [(44.0, 33.0, "Чорне море")]
# тип → (зони, максимальна дальність км)
ZONES = {
    "banderol": (CRIMEA + BELGOROD_KURSK_BRYANSK + AZOV, 520),
    "ballistic": (CRIMEA + BELGOROD_KURSK_BRYANSK + VORONEZH, 700),
    "cruise": (CRIMEA + BELGOROD_KURSK_BRYANSK + BLACK_SEA + AZOV, 1800),
    "geran5": (BELGOROD_KURSK_BRYANSK + CRIMEA + AZOV, 900),
    "rszv": (BELGOROD_KURSK_BRYANSK, 120),
}


def nearest(typ: str, la: float, lo: float):
    """(lat, lon, назва, км) найближчої досяжної зони пуску для типу або None."""
    from .geo import dist_km, to_xy
    spec = ZONES.get(typ)
    if not spec:
        return None
    zs, reach = spec
    best = min(((dist_km(to_xy(z[0], z[1]), to_xy(la, lo)), z) for z in zs), key=lambda x: x[0])
    return (best[1][0], best[1][1], best[1][2], best[0]) if best[0] <= reach else None
