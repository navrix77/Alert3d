"""Голосові заготовки Sky Radio (04.11, пропозиція власника): повідомлення складається з готових озвучених фраз —
«Увага!», «два шахеди», «на північному сході, за двадцять кілометрів від вас», «наближається», «Місце: Чугуїв».
Кожна фраза синтезується один раз і лежить у кеші, далі голос лише склеюється: без очікування моделі й синтезу,
без витрат на кожне оновлення. Словник закритий (типи × кількість, сторона × відстань, хвилини), лише назви місць
додаються в кеш при першій появі."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time

log = logging.getLogger("voicekit")

# (однина, множина після 2–4, множина після 5+, рід числівника для 1–2: m/f)
TYPES = {
    "shahed": ("шахед", "шахеди", "шахедів", "m"), "jet": ("реактивний безпілотник", "реактивні безпілотники", "реактивних безпілотників", "m"),
    "cruise": ("крилата ракета", "крилаті ракети", "крилатих ракет", "f"), "ballistic": ("балістична ракета", "балістичні ракети", "балістичних ракет", "f"),
    "kab": ("керована авіабомба", "керовані авіабомби", "керованих авіабомб", "f"), "molniya": ("«Молнія»", "«Молнії»", "«Молній»", "f"),
    "lancet": ("«Ланцет»", "«Ланцети»", "«Ланцетів»", "m"), "recon": ("розвідувальний дрон", "розвідувальні дрони", "розвідувальних дронів", "m"),
    "geran5": ("«Герань-5»", "«Герані-5»", "«Гераней-5»", "f"), "banderol": ("крилата ракета «Бандероль»", "«Бандеролі»", "«Бандеролей»", "f"),
    "fpv": ("FPV-дрон", "FPV-дрони", "FPV-дронів", "m"), "fpvf": ("FPV-дрон на оптоволокні", "FPV-дрони на оптоволокні", "FPV-дронів на оптоволокні", "m"),
    "rszv": ("РСЗВ", "РСЗВ", "РСЗВ", "f"),
}
U = ["", "один", "два", "три", "чотири", "п'ять", "шість", "сім", "вісім", "дев'ять", "десять", "одинадцять", "дванадцять", "тринадцять",
     "чотирнадцять", "п'ятнадцять", "шістнадцять", "сімнадцять", "вісімнадцять", "дев'ятнадцять"]
T = ["", "", "двадцять", "тридцять", "сорок", "п'ятдесят", "шістдесят", "сімдесят", "вісімдесят", "дев'яносто"]
H = ["", "сто", "двісті", "триста", "чотириста", "п'ятсот"]


def num(n: int, g: str = "m") -> str:
    n = int(n)
    if n <= 0:
        return "нуль"
    parts = []
    if n >= 100:
        parts.append(H[min(5, n // 100)]); n %= 100
    if n >= 20:
        parts.append(T[n // 10]); n %= 10
    if n:
        w = U[n]
        if g == "f" and n in (1, 2):
            w = "одна" if n == 1 else "дві"
        parts.append(w)
    return " ".join(parts)


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def count_type(n: int, typ: str) -> str:
    one, few, many, g = TYPES.get(typ, ("ціль", "цілі", "цілей", "f"))
    n = max(1, min(int(n or 1), 60))
    return cap(one) if n == 1 else cap(num(n, g) + " " + plural(n, one, few, many))


def km_round(km: float) -> int:
    km = max(1, round(km))
    return km if km <= 10 else int(5 * round(km / 5))


def dist(km: float) -> str:
    k = km_round(km)
    return f"за {num(k)} {plural(k, 'кілометр', 'кілометри', 'кілометрів')} від вас."


def side_dist(side: str, km: float) -> str:  # текст для екрана; у голосі — дві заготовки: сторона + відстань
    return f"{side}, {dist(km)}"


RGEN = {10: "десяти", 25: "двадцяти п'яти", 50: "п'ятдесяти", 100: "ста"}  # родовий відмінок: «у радіусі двадцяти п'яти кілометрів»


def dur(sec: float) -> str:
    """Тривалість у знахідному відмінку, округлена до 5 хв: «одну годину двадцять хвилин»."""
    m = max(5, int(5 * round(sec / 300)))
    h, mm = divmod(m, 60)
    out = []
    if h:
        out.append(f"{num(h, 'f').replace('одна', 'одну')} {plural(h, 'годину', 'години', 'годин')}")
    if mm:
        out.append(f"{num(mm, 'f').replace('одна', 'одну')} {plural(mm, 'хвилину', 'хвилини', 'хвилин')}")
    return " ".join(out)


def radius_none(r: int) -> str:
    return f"У радіусі {RGEN.get(r, num(r))} кілометрів повідомлень про цілі немає."


def eta(m: int) -> str:
    m = max(1, min(int(m), 90))
    return f"Орієнтовно {num(m, 'f')} {plural(m, 'хвилина', 'хвилини', 'хвилин')}."


def more(n: int) -> str:
    return f"Поруч ще {num(n, 'f')} {plural(n, 'ціль', 'цілі', 'цілей')}."


FIXED = ["Ви слухаєте Скай Радіо.", "Повідомлень про цілі поруч немає.", "Без змін."]
SIDES = ["на півночі", "на північному сході", "на сході", "на південному сході", "на півдні", "на південному заході", "на заході", "на північному заході"]


REG = {"Вінницька": "Вінниччина", "Волинська": "Волинь", "Луганська": "Луганщина", "Дніпропетровська": "Дніпропетровщина",
       "Донецька": "Донеччина", "Житомирська": "Житомирщина", "Закарпатська": "Закарпаття", "Запорізька": "Запоріжжя",
       "Івано-Франківська": "Івано-Франківщина", "Київська": "Київщина", "Кіровоградська": "Кіровоградщина", "Крим": "Крим",
       "Львівська": "Львівщина", "Миколаївська": "Миколаївщина", "Одеська": "Одещина", "Полтавська": "Полтавщина",
       "Рівненська": "Рівненщина", "Сумська": "Сумщина", "Тернопільська": "Тернопільщина", "Харківська": "Харківщина",
       "Херсонська": "Херсонщина", "Хмельницька": "Хмельниччина", "Черкаська": "Черкащина", "Чернігівська": "Чернігівщина",
       "Чернівецька": "Буковина", "Київ": "Київ"}
OBL_FIXED: list[str] = []
TOPW = {k: v[1] for k, v in TYPES.items()}


def reg(o: str) -> str:
    return REG.get(o, o)


def alerts_n(n: int) -> str:
    return f"Областей з тривогою: {num(n, 'f')}."


def vocabulary() -> list[str]:
    """Закритий словник заготовок: синтезується наперед, щоб перше ж оновлення звучало без очікування."""
    v = list(FIXED) + LIB + [radius_none(r) for r in (10, 25, 50, 100)] + [ago(m) for m in range(3, 61)] + [ago(m, "Останнє повідомлення") for m in range(3, 31)]
    for typ in ("shahed", "jet", "cruise", "ballistic", "kab"):
        v += [count_type(n, typ) + "." for n in range(1, 21)]
    for typ in TYPES:
        if typ not in ("shahed", "jet", "cruise", "ballistic", "kab"):
            v += [count_type(n, typ) + "." for n in (1, 2, 3)]
    kms = list(range(1, 11)) + list(range(15, 205, 5))
    v += [s + "," for s in SIDES] + [dist(k) for k in kms]
    v += [eta(m) for m in range(1, 31)] + [more(n) for n in range(1, 11)]
    # «Моя область» і «Вся Україна»
    v += OBL_FIXED + [reg(o) + "." for o in REG] + [reg(o) + "," for o in REG] + [alerts_n(n) for n in range(1, 26)]
    v += [f"переважно {w}." for w in TOPW.values()] + [cap(w) + "." for w in TOPW.values()]
    v = list(dict.fromkeys(v))
    v += LIVE_FIXED + [_cnt(l, n) for l in ("Нових цілей", "Змінилось", "Зникли з мапи") for n in range(1, 11)]
    return v


def kyiv(t: float | None) -> str:
    import datetime as _dt
    from zoneinfo import ZoneInfo
    return _dt.datetime.fromtimestamp(t or time.time(), ZoneInfo("Europe/Kyiv")).strftime("%H:%M")


def pick(key, opts: list[str]) -> str:
    """Варіант формулювання — стабільний для однієї події (не випадкове чергування); усі варіанти є в словнику."""
    return opts[int(hashlib.md5(str(key).encode()).hexdigest(), 16) % len(opts)]


class Msg:
    """Одне повідомлення радіо у двох версіях: голос (заготовки) і розширений текст для екрана (точний час, назви джерел)."""

    def __init__(self) -> None:
        self.v: list[str] = []
        self.s: list[str] = []

    def __call__(self, voice, screen: str | None = None) -> None:
        vs = [voice] if isinstance(voice, str) else [x for x in voice if x]
        self.v += vs
        txt = screen if screen is not None else " ".join(vs)
        if txt:
            self.s.append(txt.strip())

    def __bool__(self) -> bool:
        return bool(self.v)

    def out(self) -> dict:
        import re
        t = " ".join(self.s)
        t = re.sub(r"\s+", " ", t)
        t = re.sub(r"(^|[.!?]\s)([а-яіїєґ])", lambda m: m.group(1) + m.group(2).upper(), t)
        return {"voice": list(self.v), "text": t.strip()}


# ---- фрази бібліотеки (усі — у словнику заготовок, озвучуються один раз)
OPEN_NEAR = ["Зібрали останні повідомлення для вашої місцевості.", "Спочатку про обстановку поруч, далі коротко по області."]
OPEN_COUNTRY = ["Скай. Огляд повітряної обстановки по Україні.", "Спочатку головні повідомлення, потім зміни за регіонами."]
from .radio_spec import IDENTS as _IDENTS  # noqa: E402

LIB = OPEN_NEAR + OPEN_COUNTRY + list(_IDENTS.values()) + [
    "Ви слухаєте Скай.", "Далі головні зміни по Україні.", "Тепер коротко по області.", "Окреме повідомлення стосується вашої місцевості.",
    "Є уточнення до попереднього зведення.",
    # тривога
    "У вашій області оголошено повітряну тривогу.", "Перейдіть в укриття.", "Далі повідомлятимемо про зміни поруч з вами.",
    "Повітряна тривога в області триває", "Офіційного відбою немає.", "У вашому районі повітряна тривога.",
    "В області тривога діє в окремих районах.", "Для вашої геомітки тривоги немає.",
    "В області офіційно оголошено відбій повітряної тривоги.", "Повідомлення стосується саме цієї території.",
    "Офіційної тривоги в області немає.", "Тривога діє в районі, але не у вашій громаді.", "Для вашої геомітки офіційної тривоги немає.",
    # ціль поруч
    "Поблизу вашої геомітки:", "Поруч з вами нове повідомлення:", "Останнє назване місце:",
    "Це відстань до названого місця, поточне положення цілі не уточнене.",
    "Джерела не називають точного місця.", "За оцінкою Скай:", "Це розрахункова оцінка, а не нове спостереження.",
    "У повідомленні зазначено рух у напрямку:", "Джерела повідомляють про рух у напрямку:", "Поточного місця джерела не називають.",
    "Напрямок змінився.", "Раніше джерела вказували:", "У новому повідомленні:",
    "Наближається до вас.", "Рухається не до вас.", "Перейдіть в укриття.",
    "Інформація давно не оновлювалась.", "Позначка показує останнє повідомлення, а не підтверджене поточне місце.",
    "Для решти повідомлень нових уточнень місця не надходило.",
    # джерела
    "За даними Повітряних сил.", "За офіційними даними.", "Про це повідомляють кілька незалежних джерел.",
    "Повідомлення підтверджують кілька незалежних джерел.", "Поки про це повідомив один моніторинговий канал.",
    "Незалежного підтвердження поки немає.", "Джерела по-різному описують цю ціль.", "Наводимо найпізніше повідомлення.",
    # кількість, решта
    "Також:", "Найближча ціль:", "Рухається у ваш бік.", "За повідомленнями в області:",
    # КАБи, авіація, пуски
    "Повідомляють про загрозу застосування керованих авіабомб:", "Надійшло повідомлення про активність тактичної авіації біля вашої області.",
    "Зафіксовано старт.", "в повітрі.", "Старт з району:", "Повідомлення про зліт носіїв:", "Про запуск ракет у ньому не сказано.",
    "Повідомлення про загрозу балістики для вашої області. Будьте в укритті.", "Увага!",
    # область
    "Головні зміни стосуються:", "По області одне суттєве оновлення.", "Решту вже озвучених повідомлень не повторюємо.",
    "Повітряна тривога на всю область.", "Тривога в районах:", "Повідомлень про цілі в області немає.", "З сусідніх областей:",
    "Точне місце не назване.",
    # Україна
    "Офіційних тривог зараз немає.", "Загроза балістики:", "Найбільше повідомлень надходить з:", "Повідомлення про КАБи:",
    "Нові тривоги:", "Відбій тривоги:", "Докладніше про вашу місцевість можна послухати в режимі Поруч або Моя область.",
    # збої
    "Частина моніторингових джерел тимчасово недоступна.", "Зведення може бути неповним.", "Офіційні тривоги надходять.",
    "Отримання повідомлень відновлено.", "Перевіряємо актуальність і готуємо оновлене зведення.", "Без змін.",
]


def ago(m: int, what: str = "Місце названо") -> str:
    m = max(1, min(int(m), 90))
    return f"{what} {num(m, 'f').replace('одна', 'одну').replace('дві', 'дві')} {plural(m, 'хвилину', 'хвилини', 'хвилин')} тому."


def _n(x: dict) -> int:
    w = str(x.get("word", "1")).split()
    return int(w[0]) if w and w[0].isdigit() else int(x.get("n") or 1)


def status_block(m: Msg, f: dict, prev: bool | None) -> None:
    """Офіційний статус: оголошено / триває (з тривалістю) / діє в окремих районах / відбій / немає."""
    now_al = bool(f.get("alert") or f.get("raion_alert"))
    if now_al and prev is False:
        m(["У вашій області оголошено повітряну тривогу.", "Перейдіть в укриття.", "Далі повідомлятимемо про зміни поруч з вами."],
          f"У вашій області оголошено повітряну тривогу ({kyiv(None)}). Перейдіть в укриття.")
        return
    if not now_al and prev:
        m(["В області офіційно оголошено відбій повітряної тривоги.", "Повідомлення стосується саме цієї території."],
          f"В області офіційно оголошено відбій повітряної тривоги о {kyiv(None)}. Повідомлення стосується саме цієї території.")
        return
    if f.get("raion_alert"):
        m("У вашому районі повітряна тривога.", f"У вашому районі ({f.get('raion') or ''}) повітряна тривога.".replace(" ()", ""))
    elif f.get("city_free"):
        m(["Тривога діє в районі, але не у вашій громаді.", "Для вашої геомітки офіційної тривоги немає."],
          "Тривога діє в районі, але ваша громада (місто) має окремий офіційний статус: для вашої геомітки тривоги немає.")
        return
    elif f.get("alert") and f.get("partial"):
        m(["В області тривога діє в окремих районах.", "Для вашої геомітки тривоги немає."])
        return
    elif not f.get("alert"):
        m("Офіційної тривоги в області немає.")
        return
    a = f.get("alert_for")
    if a and a >= 300:
        st = kyiv(time.time() - a)
        m(["Повітряна тривога в області триває", f"вже {dur(a)}.", "Офіційного відбою немає."],
          f"Повітряна тривога в області триває з {st}. Станом на {kyiv(None)} офіційного відбою немає.")
    elif f.get("alert") and not f.get("raion_alert"):
        m(["Повітряна тривога в області триває", "Офіційного відбою немає."], "Повітряна тривога в області триває. Офіційного відбою немає.")


def source_block(m: Msg, x: dict) -> None:
    src = x.get("src") or ""
    names = x.get("src_names") or []
    if src.startswith("Повітряні сили"):
        m("За даними Повітряних сил.")
    elif src.startswith("офіційне"):
        m("За офіційними даними.")
    elif src.startswith("кілька"):
        m(pick(x.get("id") or x.get("type"), ["Про це повідомляють кілька незалежних джерел.", "Повідомлення підтверджують кілька незалежних джерел."]),
          "Про це повідомляють кілька незалежних джерел" + (f": {', '.join(names[:4])}." if names else "."))
    elif src.startswith("моніторинговий"):
        m(["Поки про це повідомив один моніторинговий канал.", "Незалежного підтвердження поки немає."],
          f"Наразі про це повідомив один моніторинговий канал{', ' + names[0] if names else ''}. Незалежного підтвердження серед доступних SKY повідомлень поки немає.")
    if x.get("contra"):
        m(["Джерела по-різному описують цю ціль.", "Наводимо найпізніше повідомлення."],
          "Джерела по-різному описують цю ціль (напрямок, кількість або місце). Наводимо найпізніше повідомлення; підстав об'єднати їх немає.")


def target_block(m: Msg, x: dict, prev_next: str | None, first_word: str) -> None:
    """Головна ціль поруч: що, де (назване місце чи оцінка SKY), давність, напрямок і його зміна, чи до вас, джерело."""
    m([first_word, count_type(_n(x), x["type"]) + "."],
      f"{first_word} {count_type(_n(x), x['type']).lower()}.")
    if x.get("at") and x.get("named_km") is not None:
        m(["Останнє назване місце:", f"{x['at']}.", x["side"] + ",", dist(x["named_km"])],
          f"Останнє назване місце: {x['at']}, {x['side']}, приблизно {x['named_km']} км від вашої геомітки"
          + (f" (повідомлення о {kyiv(time.time() - x['fix_min'] * 60)})." if x.get("fix_min") is not None else "."))
        fm = x.get("fix_min")
        if fm is not None and fm >= 3:
            m(ago(fm, "Місце названо"), "")  # на екрані вже є точний час повідомлення
            m("Це відстань до названого місця, поточне положення цілі не уточнене.")
        if fm is not None and fm >= 20:
            m(["Інформація давно не оновлювалась.", "Позначка показує останнє повідомлення, а не підтверджене поточне місце."])
        if x.get("next"):
            m(["У повідомленні зазначено рух у напрямку:", f"{x['next']}."], f"Напрямок у повідомленні: {x['next']}.")
    elif x.get("next"):
        m(["Джерела повідомляють про рух у напрямку:", f"{x['next']}.", "Поточного місця джерела не називають."],
          f"Джерела повідомляють напрямок: {x['next']}, але поточного місця не називають.")
        m(["За оцінкою Скай:", x["side"] + ",", dist(x["km"]), "Це розрахункова оцінка, а не нове спостереження."],
          f"За оцінкою SKY: {x['side']}, близько {x['km']} км від вас. Це розрахункова оцінка, а не нове спостереження.")
    else:
        m(["Джерела не називають точного місця.", "За оцінкою Скай:", x["side"] + ",", dist(x["km"]), "Це розрахункова оцінка, а не нове спостереження."],
          f"Джерела не називають точного місця. За оцінкою SKY: {x['side']}, близько {x['km']} км від вас.")
    if prev_next and x.get("next") and prev_next != x["next"]:
        m(["Напрямок змінився.", "Раніше джерела вказували:", f"{prev_next}.", "У новому повідомленні:", f"{x['next']}."],
          f"Напрямок змінився: раніше джерела вказували {prev_next}, у новому повідомленні: {x['next']}.")
    if x.get("appr"):
        v = ["Наближається до вас."]
        if x.get("eta") and x["eta"] <= 30:
            v.append(eta(x["eta"]))
        if x["km"] <= 15:
            v.append("Перейдіть в укриття.")
        m(v, "Наближається до вас" + (f", орієнтовно {x['eta']} хв." if x.get("eta") and x["eta"] <= 30 else ".")
          + (" Перейдіть в укриття." if x["km"] <= 15 else ""))
    elif x.get("appr") is False:
        m("Рухається не до вас.")
    source_block(m, x)


def area_block(m: Msg, f: dict, local: bool = True) -> None:
    """КАБи й авіація біля області, пуски й зльоти носіїв (аеродром і район пуску — з різних полів, не підмінюємо)."""
    if local and f.get("kab"):
        m(["Повідомляють про загрозу застосування керованих авіабомб:"] + [f"{x}." for x in f["kab"][:4]],
          "Повідомляють про загрозу застосування керованих авіабомб: " + ", ".join(f["kab"][:6]) + ".")
    elif local and f.get("avia"):
        m("Надійшло повідомлення про активність тактичної авіації біля вашої області.")
    la = [x for x in (f.get("launches") or []) if x.get("stage") != "takeoff"]
    if la:
        v, s = ["Зафіксовано старт."], []
        for x in la[:3]:
            v += [cap(TOPW.get(x.get("type") or "", "ракети")) + " в повітрі.", "Старт з району:", f"{x['site']}."]
            s.append(f"{TOPW.get(x.get('type') or '', 'ракети')}, район пуску {x['site']}" + (f" ({kyiv(x['t'])})" if x.get("t") else ""))
        m(v, "Зафіксовано старт: " + "; ".join(s) + ".")
    to = [x for x in (f.get("launches") or []) if x.get("stage") == "takeoff"]
    if to:
        names = [x.get("carrier") or x["site"] for x in to[:3]]
        m(["Повідомлення про зліт носіїв:"] + [f"{n}." for n in names] + ["Про запуск ракет у ньому не сказано."],
          "Повідомлення про зліт носіїв: " + ", ".join(f"{x.get('carrier') or 'носій'} ({x['site']}{', ' + kyiv(x['t']) if x.get('t') else ''})" for x in to[:3])
          + ". Це повідомлення про активність авіації; про запуск ракет у ньому не сказано.")


def compose(f: dict, first: bool = False, greeted: bool = True, known: int = 0, status: bool = False, summary: bool = False,
            prev_al: bool | None = None, prev_next: dict | None = None, recovered: bool = False) -> dict:
    """«Поруч зі мною»: відкриття (новому слухачеві), статус тривоги, головна ціль, ще до двох, по області, пуски.
    Повертає {"voice": [заготовки], "text": розширений текст для екрана}."""
    m = Msg()
    prev_next = prev_next or {}
    if recovered:
        m(["Отримання повідомлень відновлено.", "Перевіряємо актуальність і готуємо оновлене зведення."])
    if first:
        if not greeted:
            m("Ви слухаєте Скай.")
        m(OPEN_NEAR, f"Скай. Оновлення станом на {kyiv(None)} для вашої місцевості.")
    if f.get("bal"):
        m(["Увага!", "Повідомлення про загрозу балістики для вашої області. Будьте в укритті."],
          f"Увага! Повідомлення про загрозу балістики для вашої області ({kyiv(f['bal'][0].get('t'))}). Будьте в укритті.")
    near = f.get("near") or []
    if status or summary or not near:
        status_block(m, f, prev_al)
    if near:
        x = near[0]
        lead = "Поблизу вашої геомітки:" if first or summary else pick(x.get("id") or x.get("type"), ["Поблизу вашої геомітки:", "Поруч з вами нове повідомлення:"])
        if f.get("urgent") and not f.get("bal"):
            m("Увага!")
        target_block(m, x, prev_next.get(x.get("id")), lead)
        rest = near[1:3] if summary or f.get("urgent") else []
        stale = False
        for y in rest:
            km = y["named_km"] if y.get("named_km") is not None else y["km"]
            m(["Також:", count_type(_n(y), y["type"]) + ".", y["side"] + ",", dist(km)] + (["Наближається до вас."] if y.get("appr") else []),
              f"Також: {count_type(_n(y), y['type']).lower()}" + (f" (останнє місце: {y['at']})" if y.get("at") else "") + f", {y['side']}, близько {km} км"
              + (", наближається." if y.get("appr") else "."))
            stale = stale or (y.get("fix_min") or 0) >= 20
        if stale:
            m("Для решти повідомлень нових уточнень місця не надходило.", "Для решти повідомлень нових уточнень місця не надходило; час останніх повідомлень є в картках на мапі.")
        if (f.get("n_near") or 0) > 1 + len(rest):
            m(more(min(10, f["n_near"] - 1 - len(rest))))
    elif not known:
        r = int(f.get("radius") or 0)
        m(radius_none(r) if r in (10, 25, 50, 100) else "Повідомлень про цілі поруч немає.",
          (f"У радіусі {r} км повідомлень про цілі немає" if r else "Повідомлень про цілі поруч немає") + ". Це не означає, що загрози немає.")
        x = f.get("far")
        if x:
            v = ["Найближча ціль:", count_type(x["n"], x["type"]) + ".", x["side"] + ",", dist(x["km"])]
            if x.get("at"):
                v.append(f"Місце: {x['at']}.")
            if x.get("appr"):
                v.append("Рухається у ваш бік.")
            m(v, f"Найближча ціль: {count_type(x['n'], x['type']).lower()}" + (f" (останнє місце: {x['at']})" if x.get("at") else "") +
              f", {x['side']}, близько {x['km']} км" + (", рухається у ваш бік." if x.get("appr") else "."))
    if summary and (f.get("obl_types") or f.get("kab") or f.get("avia")):
        m("Тепер коротко по області.")
        if f.get("obl_types"):
            m(["За повідомленнями в області:"] + [cap(TOPW.get(t, "цілі")) + "." for t in f["obl_types"][:4]],
              "За повідомленнями в області: " + ", ".join(TOPW.get(t, "цілі") for t in f["obl_types"][:6]) + ".")
    if summary or f.get("urgent"):
        area_block(m, f)
    return m.out()


def compose_oblast(f: dict, status: bool = True, empty: bool | None = None, first: bool = True, skipped: int = 0) -> dict:
    """«Моя область»: назва, статус по районах (без узагальнення на всю область), головні зміни за районами."""
    m = Msg()
    groups = [(r, it) for r, it in (f.get("groups") or {}).items()]
    groups.sort(key=lambda g: (g[0].startswith("з "), -len(g[1])))
    if first:
        m(reg(f["obl"]) + ".", f"{reg(f['obl'])}. Станом на {kyiv(None)}.")
    if status:
        if f.get("whole"):
            m("Повітряна тривога на всю область.")
        elif f.get("al_raions"):
            m(["Тривога в районах:"] + [f"{r} район." for r in f["al_raions"][:6]], "Тривога діє в районах: " + ", ".join(f["al_raions"]) + ".")
        else:
            m("Офіційної тривоги в області немає.")
    if len(groups) == 1 and not first:
        m("По області одне суттєве оновлення.")
    elif groups:
        names = [("з сусідніх областей" if r.startswith("з ") else f"{r} район") for r, _ in groups[:3]]
        m("Головні зміни стосуються:", "Головні зміни стосуються: " + ", ".join(names) + ".")
    for r, items in groups[:3]:
        head = "З сусідніх областей:" if r.startswith("з ") else f"{r} район." if r != "район не визначено" else "Окреме повідомлення стосується вашої місцевості."
        by: dict = {}
        for x in items:
            by[x.get("type", "shahed")] = by.get(x.get("type", "shahed"), 0) + (x.get("n") or 1)
        v = [head] + [count_type(n, typ) + "." for typ, n in sorted(by.items(), key=lambda kv: -kv[1])[:2]]
        at = next((x["at"] for x in items if x.get("at")), None)
        v.append(f"Останнє назване місце: {at}." if at else ("Точне місце не назване." if not r.startswith("з ") else ""))
        nx = next((x.get("next") for x in items if x.get("next")), None)
        m(v, f"{head.rstrip('.:')}: " + ", ".join(count_type(n, typ).lower() for typ, n in sorted(by.items(), key=lambda kv: -kv[1])[:3]) +
          (f"; останнє назване місце {at}" if at else "; точне місце не назване, положення оцінене SKY" if not r.startswith("з ") else "") +
          (f"; напрямок на {nx}" if nx else "") + ".")
    if skipped:
        m("Решту вже озвучених повідомлень не повторюємо.")
    if not groups and (empty if empty is not None else True):
        m("Повідомлень про цілі в області немає.", "Повідомлень про цілі в області немає. Це не означає, що загрози немає.")
    return m.out()


def _country_body(m: Msg, f: dict) -> None:
    if f.get("bal"):
        m(["Загроза балістики:"] + [reg(o) + "." for o in f["bal"][:4]], "Загроза балістики: " + ", ".join(reg(o) for o in f["bal"]) + ".")
    m(alerts_n(len(f["al"])) if f.get("al") else "Офіційних тривог зараз немає.",
      (f"Областей з тривогою: {len(f['al'])}." if f.get("al") else "Офіційних тривог зараз немає."))
    if f.get("types"):
        m(["У повітрі за повідомленнями:"] + [cap(TOPW.get(t, "цілі")) + "." for t in f["types"][:5]],
          "У повітрі за повідомленнями моніторингу: " + ", ".join(TOPW.get(t, "цілі") for t in f["types"]) + ".")
    area_block(m, f, local=False)
    if f.get("kab_obl"):
        m(["Повідомлення про КАБи:"] + [reg(o) + "." for o in f["kab_obl"][:4]], "Повідомлення про КАБи: " + ", ".join(reg(o) for o in f["kab_obl"]) + ".")
    if f.get("top"):
        v, s = ["Найбільше повідомлень надходить з:"], []
        for o, ty in f["top"][:3]:
            v += [reg(o) + ",", f"переважно {TOPW.get(ty[0][0], 'цілі')}."] if ty else [reg(o) + "."]
            s.append(reg(o) + (f" (переважно {TOPW.get(ty[0][0], 'цілі')})" if ty else ""))
        m(v, "Найбільше повідомлень надходить з: " + "; ".join(s) + ". Це кількість дописів, а не оцінка небезпеки.")


def compose_country(f: dict, after_local: bool = False) -> dict:
    """«Вся Україна»: повний огляд. Після місцевого зведення — з переходом «Далі головні зміни по Україні»."""
    m = Msg()
    if after_local:
        m("Далі головні зміни по Україні.", f"Україна, станом на {kyiv(None)}.")
    else:
        m(OPEN_COUNTRY, f"Скай. Огляд повітряної обстановки по Україні станом на {kyiv(None)}.")
    _country_body(m, f)
    if not after_local:
        m("Докладніше про вашу місцевість можна послухати в режимі Поруч або Моя область.")
    return m.out()


def compose_changes(f: dict, prev: dict) -> dict:
    """«Вся Україна» між оглядами: лише головні зміни за регіонами."""
    m = Msg()
    new_al = [o for o in f["al"] if o not in prev.get("al", [])]
    gone_al = [o for o in prev.get("al", []) if o not in f["al"]]
    nb = [o for o in f.get("bal", []) if o not in prev.get("bal", [])]
    if nb:
        m(["Загроза балістики:"] + [reg(o) + "." for o in nb[:4]])
    if new_al:
        m(["Нові тривоги:"] + [reg(o) + "." for o in new_al[:5]], "Нові тривоги: " + ", ".join(reg(o) for o in new_al) + ".")
    if gone_al:
        m(["Відбій тривоги:"] + [reg(o) + "." for o in gone_al[:5]], "Відбій тривоги: " + ", ".join(reg(o) for o in gone_al) + ".")
    pk = set(map(tuple, prev.get("la", [])))
    nl = [x for x in f.get("launches") or [] if (x.get("type"), x.get("site"), x.get("stage")) not in pk]
    area_block(m, {"launches": nl}, local=False)
    nk = [o for o in f.get("kab_obl") or [] if o not in prev.get("kab", [])]
    if nk:
        m(["Повідомлення про КАБи:"] + [reg(o) + "." for o in nk[:4]])
    nt = [(o, ty) for o, ty in f.get("top", [])[:3] if o not in prev.get("top", [])]
    if nt:
        v = ["Найбільше повідомлень надходить з:"]
        for o, ty in nt:
            v += [reg(o) + ",", f"переважно {TOPW.get(ty[0][0], 'цілі')}."] if ty else [reg(o) + "."]
        m(v)
    if not m:
        return {"voice": [], "text": ""}
    out = Msg()
    out("Далі головні зміни по Україні.", f"Україна, зміни станом на {kyiv(None)}.")
    out.v += m.v
    out.s += m.s
    return out.out()


def compose_outage(official_ok: bool) -> dict:
    m = Msg()
    m(["Частина моніторингових джерел тимчасово недоступна.", "Зведення може бути неповним."] + (["Офіційні тривоги надходять."] if official_ok else []))
    return m.out()


def vocab_lib() -> list[str]:
    return list(LIB)


# ---------- Ефір «що змінилось» без моделі: кроки для мапи + голос із заготовок
def _cnt(label: str, n: int) -> str:
    return f"{label}: {num(min(int(n), 60), 'f')}."


LIVE_FIXED = ["Що змінилось біля вас.", "Суттєвих змін у вашому районі немає.", "Відбій балістики.", "Нова ціль.",
              "Кількість змінилась."]


def live_steps(d: dict) -> list[dict]:
    """Ефір «що змінилось» за бібліотекою сценаріїв: кожен крок — say (розширений текст для екрана) і voice (заготовки).
    Без моделі й без нового синтезу. Зникнення з мапи — нейтрально, не як збиття й не як відбій."""
    c = d["counts"]
    steps = []
    m = Msg()
    mins = d.get("minutes") or 0
    m("Що змінилось біля вас.", f"Що змінилось біля вас{f' за {mins} хв' if mins else ''} (станом на {kyiv(d.get('now'))}).")
    al = d.get("alert")
    if al and al["now"] != al["was"]:
        status_block(m, {"alert": al["now"]}, al["was"])
    parts = []
    if c["new"]:
        m(_cnt("Нових цілей", c["new"]), f"Нових цілей: {c['new']}."); parts.append(1)
    if c["changed"]:
        m(_cnt("Змінилось", c["changed"]), f"Змінилось: {c['changed']}."); parts.append(1)
    if c["gone"]:
        m(_cnt("Зникли з мапи", c["gone"]), f"Зникли з мапи: {c['gone']}. Нових повідомлень про них немає; це не означає збиття.")
        parts.append(1)
    if not parts and not (al and al["now"] != al["was"]):
        m("Суттєвих змін у вашому районі немає.", "Суттєвих змін у вашому районі немає. Це не означає, що загрози немає.")
    o = m.out()
    steps.append({"say": o["text"], "action": "overview", "voice": o["voice"]})
    if d.get("bal"):
        b = d["bal"][-1]
        m = Msg()
        if b.get("close"):
            m("Відбій балістики.", f"Відбій загрози балістики о {kyiv(b['t'])}.")
        else:
            m(["Увага!", "Повідомлення про загрозу балістики для вашої області. Будьте в укритті."],
              f"Увага! Повідомлення про загрозу балістики о {kyiv(b['t'])}. Будьте в укритті.")
        o = m.out()
        steps.append({"say": o["text"], "action": "dim", "value": True, "voice": o["voice"]})
    for it in [i for i in d["items"] if i["status"] in ("new", "changed")][:5]:
        m = Msg()
        n = it["count"]
        if it["status"] == "new":
            m([count_type(n, it["type"]) + ".", "Нова ціль."], f"{count_type(n, it['type'])}: нова ціль.")
        elif it.get("count_was") and it["count_was"] != n:
            m(["Кількість змінилась.", count_type(n, it["type"]) + "."],
              f"Кількість змінилась: було {it['count_was']}, стало {n} ({TOPW.get(it['type'], 'цілі')}).")
        else:
            m(count_type(n, it["type"]) + ".", f"{count_type(n, it['type'])}: оновлення.")
        if it.get("next") and it.get("next_was") and it["next"] != it["next_was"]:
            m(["Напрямок змінився.", "Раніше джерела вказували:", f"{it['next_was']}.", "У новому повідомленні:", f"{it['next']}."],
              f"Напрямок змінився: раніше джерела вказували {it['next_was']}, у новому повідомленні: {it['next']}.")
        elif it.get("next"):
            m(["У повідомленні зазначено рух у напрямку:", f"{it['next']}."], f"Напрямок у повідомленні: {it['next']}.")
        if it.get("km") is not None:
            m(dist(it["km"]), f"Приблизно {it['km']} км від вашої геомітки.")
        ms = it.get("mentions") or []
        if ms:
            last = ms[-1]
            mm = max(1, round(((d.get("now") or time.time()) - last["t"]) / 60))
            if mm >= 3:
                m(ago(mm, "Останнє повідомлення"), f"Останнє повідомлення о {kyiv(last['t'])}, {last.get('name') or last['src']}.")
            else:
                m([], f"Останнє повідомлення о {kyiv(last['t'])}, {last.get('name') or last['src']}.")
            prim = list(dict.fromkeys(e.get("name") or e["src"] for e in ms if not e.get("copy")))
            copies = sum(1 for e in ms if e.get("copy"))
            if len(prim) >= 2:
                m(pick(it["id"], ["Про це повідомляють кілька незалежних джерел.", "Повідомлення підтверджують кілька незалежних джерел."]),
                  "Про це повідомляють кілька незалежних джерел: " + ", ".join(prim[:4]) + ".")
            elif len(prim) == 1:
                m(["Поки про це повідомив один моніторинговий канал.", "Незалежного підтвердження поки немає."],
                  f"Наразі про це повідомив один моніторинговий канал, {prim[0]}. Незалежного підтвердження поки немає."
                  + (f" Ще {copies} {plural(copies, 'канал лише поширив', 'канали лише поширили', 'каналів лише поширили')} це повідомлення." if copies else ""))
        act = "breakdown" if it.get("count_was") and it["count_was"] != n else "focus"
        o = m.out()
        steps.append({"say": o["text"], "action": act, "ids": [it["id"]], "voice": o["voice"]})
    return steps


# ---------- голосові сповіщення: текст картки → заготовки (числа округлені, щоб фраз було мало й вони повторювались)
def _km_words(n: int) -> str:
    k = km_round(n)
    return f"{num(k)} {plural(k, 'кілометр', 'кілометри', 'кілометрів')}"


def alert_frags(text: str) -> list[str]:
    """«Шахед ×2, курс на ваш район. 24 км з півдня, ~8 хв» → ["Шахед.", "Дві цілі.", "Курс на ваш район.",
    "Двадцять п'ять кілометрів з півдня.", "Приблизно вісім хвилин."]. Кожна фраза озвучується один раз на голос і далі з кешу."""
    import re
    t = " ".join(str(text or "").split())
    t = re.sub(r"^[^\wА-Яа-яІіЇїЄєҐґ«]+", "", t)
    t = t.replace("~", "приблизно ").replace("·", ",").replace("→", "на").replace("—", ",")
    t = re.sub(r"(\w+)\s+обл\.?(?=$|[\s,.])", r"\1 область", t)
    t = re.sub(r"\s*×\s*(\d+)", lambda m: ", " + num(int(m[1]), "f") + " " + plural(int(m[1]), "ціль", "цілі", "цілей"), t)
    t = re.sub(r"(\d+)\s*км\b", lambda m: _km_words(int(m[1])), t)
    t = re.sub(r"(?:приблизно\s+)?(\d+)\s*хв\b", lambda m: "приблизно " + num(max(1, int(m[1])), "f") + " " +
               plural(max(1, int(m[1])), "хвилина", "хвилини", "хвилин"), t)
    t = re.sub(r"\b(\d{1,3})\b", lambda m: num(int(m[1])), t)
    out = []
    for p in re.split(r"[.,;:!?]+\s*", t):
        p = p.strip(" -")
        if p:
            out.append(cap(p) + ".")
    return out[:10]


# ---------- синтез і склейка
SEQ: dict[str, tuple[float, list[str]]] = {}


def register(frags: list[str]) -> str:
    sid = hashlib.sha1("|".join(frags).encode()).hexdigest()[:16]
    SEQ[sid] = (time.time(), frags)
    if len(SEQ) > 2000:
        for k in sorted(SEQ, key=lambda k: SEQ[k][0])[:1000]:
            SEQ.pop(k, None)
    return sid


_BR = {1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320], 2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]}
_SR = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def _frame_len(h: bytes) -> int:
    """Довжина кадру MPEG Layer III за заголовком (0 — не кадр)."""
    if len(h) < 4 or h[0] != 0xFF or (h[1] & 0xE0) != 0xE0:
        return 0
    ver = (h[1] >> 3) & 3
    if ver == 1 or ((h[1] >> 1) & 3) != 1:
        return 0
    bi, si, pad = h[2] >> 4, (h[2] >> 2) & 3, (h[2] >> 1) & 1
    if bi in (0, 15) or si == 3:
        return 0
    br = _BR[1 if ver == 3 else 2][bi] * 1000
    sr = _SR[ver][si]
    return (144 if ver == 3 else 72) * br // sr + pad


def _strip_id3(b: bytes) -> bytes:
    """Прибирає ID3 і службовий кадр Xing/Info: інакше телефон бере тривалість першої фрази за тривалість усієї склейки
    і обриває звук (04.11: «обриває текст не доказавши речення»)."""
    if b[:3] == b"ID3" and len(b) > 10:
        size = (b[6] << 21) | (b[7] << 14) | (b[8] << 7) | b[9]
        b = b[10 + size:]
    i = 0
    while i < min(len(b), 4096) and _frame_len(b[i:i + 4]) == 0:
        i += 1
    n = _frame_len(b[i:i + 4])
    if n and (b"Xing" in b[i:i + n] or b"Info" in b[i:i + n] or b"VBRI" in b[i:i + n]):
        return b[i + n:]
    return b[i:] if n else b


async def render(frags: list[str], say) -> tuple[bytes | None, str]:
    """Склеює озвучені заготовки в одне mp3. Якщо хоч одна фраза не mp3 (запасний голос) — None, клієнт озвучить текст цілком.
    say(text) -> (bytes, by): озвучка з обліком символів (main._say)."""
    sem = asyncio.Semaphore(8)  # не більше 4 нових синтезів водночас: 40 паралельних запитів провайдер відкидає (429)

    async def one(x):
        async with sem:
            for k in range(3):
                try:
                    r = await say(x)
                except Exception:  # noqa: BLE001
                    r = (None, "error")
                if r[0]:
                    return r
                await asyncio.sleep(0.3 * (k + 1))
            return r
    parts = await asyncio.gather(*(one(x) for x in frags))
    out = []
    wavs = 0
    for data, _by in parts:
        if not data:
            return None, "missing"
        if data[:4] == b"RIFF":
            wavs += 1
        out.append(data)
    if wavs == len(out):  # усі фрази озвучені запасним голосом (WAV): склеюємо в один WAV, якщо формат однаковий
        try:
            import io
            import wave
            ws = [wave.open(io.BytesIO(d)) for d in out]
            prm = ws[0].getparams()[:3]
            if all(w.getparams()[:3] == prm for w in ws):
                buf = io.BytesIO()
                with wave.open(buf, "wb") as o:
                    o.setparams(ws[0].getparams())
                    for w in ws:
                        o.writeframes(w.readframes(w.getnframes()))
                return buf.getvalue(), "kit-wav"
        except Exception:  # noqa: BLE001
            pass
        return None, "wav"
    if wavs:
        return None, "wav"
    return await tighten(b"".join(_strip_id3(d) for d in out)), "kit"


def _ffmpeg() -> str | None:
    import shutil
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return shutil.which("ffmpeg")


async def tighten(mp3: bytes) -> bytes:
    """07.11 власник: «великі паузи між блоками». Кожна коротка заготовка має тишу на початку й у кінці; склеєні, вони дають
    паузи по секунді. Довгу тишу стискаємо до ~0,14 с. Немає ffmpeg чи збій — віддаємо як є."""
    ff = _ffmpeg()
    if not ff or len(mp3) < 2000:
        return mp3
    try:
        pr = await asyncio.create_subprocess_exec(
            ff, "-v", "error", "-i", "pipe:0", "-af",
            "silenceremove=start_periods=1:start_silence=0.04:start_threshold=-42dB:stop_periods=-1:stop_duration=0.2:stop_silence=0.14:stop_threshold=-42dB",
            "-c:a", "libmp3lame", "-q:a", "4", "-f", "mp3", "pipe:1",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(pr.communicate(mp3), 10)
        return out if pr.returncode == 0 and len(out) > 1000 else mp3
    except Exception:  # noqa: BLE001
        return mp3


_WARM = {"state": "idle", "done": 0, "total": 0}


async def warm(say, paid_ok) -> None:
    """Фоном озвучує весь словник (≈600 коротких фраз). Уже озвучене беремо з кешу миттєво; окрема помилка не зупиняє прогрів,
    а повторюється в кінці. Паузу тримаємо лише після справжнього синтезу, щоб не впиратися в ліміт запитів."""
    v = vocabulary()
    _WARM.update(state="running", total=len(v), done=0)
    for rnd in range(3):
        miss = []
        for x in v:
            if not paid_ok():
                _WARM["state"] = "paused:cap"
                return
            try:
                data, by = await say(x)
            except Exception as e:  # noqa: BLE001
                log.warning("warm: %s", e)
                data, by = None, ""
            if not data:
                miss.append(x)
            elif rnd == 0:
                _WARM["done"] += 1
            if not str(by).endswith("cache"):
                await asyncio.sleep(0.7)
        if not miss:
            _WARM["state"] = "done"
            return
        v = miss
        await asyncio.sleep(20)
    _WARM["state"] = "partial:" + str(len(v))


def status() -> dict:
    return dict(_WARM)
