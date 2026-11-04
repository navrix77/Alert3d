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
    "geran5": ("«Герань-5»", "«Герані-5»", "«Гераней-5»", "f"), "banderol": ("«Бандероль»", "«Бандеролі»", "«Бандеролей»", "f"),
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


def eta(m: int) -> str:
    m = max(1, min(int(m), 90))
    return f"Орієнтовно {num(m, 'f')} {plural(m, 'хвилина', 'хвилини', 'хвилин')}."


def more(n: int) -> str:
    return f"Поруч ще {num(n, 'f')} {plural(n, 'ціль', 'цілі', 'цілей')}."


FIXED = ["Увага!", "Оновлення.", "Ви слухаєте Скай Радіо.", "Наближається.", "Рухається не до вас.", "Напрямок невідомий.",
         "Точне місце не назване.", "Повідомлення про загрозу балістики для вашої області. Будьте в укритті.",
         "Тривога в області триває.", "У вашому районі повітряна тривога.", "Повідомлень про цілі поруч немає.", "Без змін.",
         "Добра новина: ціль віддаляється.", "Оновлення SKY тимчасово недоступні. Стежте за офіційними сповіщеннями."]
SIDES = ["на півночі", "на північному сході", "на сході", "на південному сході", "на півдні", "на південному заході", "на заході", "на північному заході"]


REG = {"Вінницька": "Вінниччина", "Волинська": "Волинь", "Луганська": "Луганщина", "Дніпропетровська": "Дніпропетровщина",
       "Донецька": "Донеччина", "Житомирська": "Житомирщина", "Закарпатська": "Закарпаття", "Запорізька": "Запоріжжя",
       "Івано-Франківська": "Івано-Франківщина", "Київська": "Київщина", "Кіровоградська": "Кіровоградщина", "Крим": "Крим",
       "Львівська": "Львівщина", "Миколаївська": "Миколаївщина", "Одеська": "Одещина", "Полтавська": "Полтавщина",
       "Рівненська": "Рівненщина", "Сумська": "Сумщина", "Тернопільська": "Тернопільщина", "Харківська": "Харківщина",
       "Херсонська": "Херсонщина", "Хмельницька": "Хмельниччина", "Черкаська": "Черкащина", "Чернігівська": "Чернігівщина",
       "Чернівецька": "Буковина", "Київ": "Київ"}
OBL_FIXED = ["Україна, зміни.", "Нові тривоги:", "Відбій тривоги:", "Повітряна тривога на всю область.", "Тривога в районах:", "Офіційної тривоги в області немає.",
             "Повідомлень про цілі в області немає.", "З сусідніх областей:", "Огляд по Україні.", "Офіційних тривог зараз немає.",
             "Загроза балістики:", "Найбільше повідомлень про цілі:", "Більше змін немає."]
TOPW = {k: v[1] for k, v in TYPES.items()}


def reg(o: str) -> str:
    return REG.get(o, o)


def alerts_n(n: int) -> str:
    return f"Областей з тривогою: {num(n, 'f')}."


def vocabulary() -> list[str]:
    """Закритий словник заготовок: синтезується наперед, щоб перше ж оновлення звучало без очікування."""
    v = list(FIXED)
    for typ in ("shahed", "jet", "cruise", "ballistic", "kab"):
        v += [count_type(n, typ) for n in range(1, 21)]
    for typ in TYPES:
        if typ not in ("shahed", "jet", "cruise", "ballistic", "kab"):
            v += [count_type(n, typ) for n in (1, 2, 3)]
    kms = list(range(1, 11)) + list(range(15, 205, 5))
    v += [s + "," for s in SIDES] + [dist(k) for k in kms]
    v += [eta(m) for m in range(1, 31)] + [more(n) for n in range(1, 11)]
    # «Моя область» і «Вся Україна»
    v += OBL_FIXED + [reg(o) + "." for o in REG] + [reg(o) + "," for o in REG] + [alerts_n(n) for n in range(1, 26)]
    v += [f"переважно {w}." for w in TOPW.values()]
    v += LIVE_FIXED + [_cnt(l, n) for l in ("Нових цілей", "Змінилось", "Зникли з мапи") for n in range(1, 11)]
    for typ in ("shahed", "jet", "cruise", "ballistic", "kab"):
        v += [count_type(n, typ) + "." for n in range(1, 11)]
    return v


def compose_oblast(f: dict, status: bool = True, empty: bool | None = None) -> list[str]:
    """«Моя область»: назва регіону, статус тривоги (по районах, без узагальнення), цілі за районами (до трьох).
    status=False — статус уже озвучено; empty — чи в області справді немає повідомлень (а не лише нових)."""
    out = [reg(f["obl"]) + "."]
    if not status:
        pass
    elif f.get("whole"):
        out.append("Повітряна тривога на всю область.")
    elif f.get("al_raions"):
        out.append("Тривога в районах:")
        out += [f"{r} район." for r in f["al_raions"][:6]]
    else:
        out.append("Офіційної тривоги в області немає.")
    groups = [(r, it) for r, it in (f.get("groups") or {}).items()]
    groups.sort(key=lambda g: (g[0].startswith("з "), -len(g[1])))
    for r, items in groups[:3]:
        out.append("З сусідніх областей:" if r.startswith("з ") else f"{r} район." if r != "район не визначено" else "Оновлення.")
        by: dict = {}
        for x in items:
            by[x.get("type", "shahed")] = by.get(x.get("type", "shahed"), 0) + (x.get("n") or 1)
        for typ, n in sorted(by.items(), key=lambda kv: -kv[1])[:2]:
            out.append(count_type(n, typ) + ".")
        at = next((x["at"] for x in items if x.get("at")), None)
        if at:
            out.append(f"Місце: {at}.")
        elif not r.startswith("з "):
            out.append("Точне місце не назване.")  # район визначено за оцінкою положення, а не за назвою
    if not groups and (empty if empty is not None else True):
        out.append("Повідомлень про цілі в області немає.")
    return out


def compose_changes(f: dict, prev: dict) -> list[str]:
    """«Вся Україна» між оглядами: лише головні зміни за регіонами — нові тривоги, відбої, балістика, нові лідери за активністю."""
    out = []
    new_al = [o for o in f["al"] if o not in prev.get("al", [])]
    gone_al = [o for o in prev.get("al", []) if o not in f["al"]]
    if new_al:
        out += ["Нові тривоги:"] + [reg(o) + "." for o in new_al[:5]]
    if gone_al:
        out += ["Відбій тривоги:"] + [reg(o) + "." for o in gone_al[:5]]
    nb = [o for o in f.get("bal", []) if o not in prev.get("bal", [])]
    if nb:
        out += ["Загроза балістики:"] + [reg(o) + "." for o in nb[:4]]
    nt = [(o, ty) for o, ty in f.get("top", [])[:3] if o not in prev.get("top", [])]
    if nt:
        out.append("Найбільше повідомлень про цілі:")
        for o, ty in nt:
            out += [reg(o) + ",", f"переважно {TOPW.get(ty[0][0], 'цілі')}."] if ty else [reg(o) + "."]
    return (["Україна, зміни."] + out) if out else []


def compose_country(f: dict) -> list[str]:
    out = ["Огляд по Україні."]
    out.append(alerts_n(len(f["al"])) if f.get("al") else "Офіційних тривог зараз немає.")
    if f.get("bal"):
        out.append("Загроза балістики:")
        out += [reg(o) + "." for o in f["bal"][:4]]
    if f.get("top"):
        out.append("Найбільше повідомлень про цілі:")
        for o, ty in f["top"][:3]:
            if ty:
                out += [reg(o) + ",", f"переважно {TOPW.get(ty[0][0], 'цілі')}."]
            else:
                out.append(reg(o) + ".")
    return out


def compose(f: dict, first: bool = False, greeted: bool = True, known: int = 0) -> list[str]:
    """known — скільки цілей поруч уже озвучено раніше (в іншому режимі): тоді не кажемо «повідомлень немає»."""
    """Факти near_facts → послідовність заготовок. Лише те, що людині треба почути зараз: найважливіша ціль, де, чи летить сюди."""
    out: list[str] = []
    if first and not greeted:
        out.append("Ви слухаєте Скай Радіо.")
    if f.get("bal"):
        out.append("Увага!")
        out.append("Повідомлення про загрозу балістики для вашої області. Будьте в укритті.")
    near = f.get("near") or []
    if near:
        x = near[0]
        if not f.get("bal"):
            out.append("Увага!" if f.get("urgent") else "Оновлення.")
        n = int(str(x.get("word", "1")).split()[0]) if str(x.get("word", "")).split()[0].isdigit() else 1
        out.append(count_type(n, x["type"]))
        if x.get("at") and x.get("named_km") is not None:
            out += [x["side"] + ",", dist(x["named_km"]), f"Місце: {x['at']}."]
        else:
            out += [x["side"] + ",", dist(x["km"]), "Точне місце не назване."]
        if x.get("appr"):
            out.append("Наближається.")
            if x.get("eta") and x["eta"] <= 30:
                out.append(eta(x["eta"]))
        elif x.get("appr") is False:
            out.append("Рухається не до вас.")
        if x.get("next"):
            out.append(f"Курс: {x['next']}.")
        if (f.get("n_near") or 0) > 1:
            out.append(more(min(10, f["n_near"] - 1)))
    else:
        if f.get("raion_alert"):
            out.append("У вашому районі повітряна тривога.")
        elif f.get("alert"):
            out.append("Тривога в області триває.")
        if not known:
            out.append("Повідомлень про цілі поруч немає.")
    return out


# ---------- Ефір «що змінилось» без моделі: кроки для мапи + голос із заготовок
def _cnt(label: str, n: int) -> str:
    return f"{label}: {num(min(int(n), 60), 'f')}."


LIVE_FIXED = ["Що змінилось біля вас.", "Суттєвих змін у вашому районі немає.", "Оголошено повітряну тривогу.", "Тривогу знято.",
              "Повідомлення про балістику.", "Відбій балістики.", "Нова ціль.", "Кількість змінилась.", "Курс змінився.",
              "Нових повідомлень з того часу немає."]


def live_steps(d: dict) -> list[dict]:
    """Детермінований сценарій Ефіру: say — для екрана, voice — заготовки для голосу (жодних нових витрат на кожен показ)."""
    c = d["counts"]
    steps = []
    v = ["Що змінилось біля вас."]
    parts = []
    if c["new"]:
        v.append(_cnt("Нових цілей", c["new"])); parts.append(f"нових цілей {c['new']}")
    if c["changed"]:
        v.append(_cnt("Змінилось", c["changed"])); parts.append(f"змінилось {c['changed']}")
    if c["gone"]:
        v.append(_cnt("Зникли з мапи", c["gone"])); parts.append(f"зникли з мапи {c['gone']}")
    al = d.get("alert")
    if al and al["now"] != al["was"]:
        v.append("Оголошено повітряну тривогу." if al["now"] else "Тривогу знято.")
        parts.append("оголошено тривогу" if al["now"] else "тривогу знято")
    if len(v) == 1:
        v.append("Суттєвих змін у вашому районі немає.")
    m = d.get("minutes")
    steps.append({"say": (f"За {m} хв: " if m else "Зараз: ") + (", ".join(parts) if parts else "суттєвих змін у вашому районі немає") + ".",
                  "action": "overview", "voice": v})
    if d.get("bal"):
        b = d["bal"][-1]
        ph = "Відбій балістики." if b.get("close") else "Повідомлення про балістику."
        steps.append({"say": ph[:-1] + f" о {time.strftime('%H:%M', time.localtime(b['t']))}.", "action": "dim", "value": True, "voice": [ph]})
    for it in [i for i in d["items"] if i["status"] in ("new", "changed")][:5]:
        v = [count_type(it["count"], it["type"]) + "."]
        say = it["name"] + (f" ×{it['count']}" if it["count"] > 1 else "")
        if it["status"] == "new":
            v.append("Нова ціль."); say += ", нова ціль"
        elif it.get("count_was") and it["count_was"] != it["count"]:
            v.append("Кількість змінилась."); say += f": було {it['count_was']}, стало {it['count']}"
        elif it.get("next") and it["next"] != it.get("next_was"):
            v.append("Курс змінився."); say += ": курс змінився"
        if it.get("next"):
            v.append(f"Курс: {it['next']}."); say += f", курс на {it['next']}"
        if it.get("km") is not None:
            v.append(dist(it["km"])); say += f", {it['km']} км від вас"
        act = "breakdown" if it.get("count_was") and it["count_was"] != it["count"] else "focus"
        steps.append({"say": say + ".", "action": act, "ids": [it["id"]], "voice": v})
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


def _strip_id3(b: bytes) -> bytes:
    if b[:3] == b"ID3" and len(b) > 10:
        size = (b[6] << 21) | (b[7] << 14) | (b[8] << 7) | b[9]
        return b[10 + size:]
    return b


async def render(frags: list[str], say) -> tuple[bytes | None, str]:
    """Склеює озвучені заготовки в одне mp3. Якщо хоч одна фраза не mp3 (запасний голос) — None, клієнт озвучить текст цілком.
    say(text) -> (bytes, by): озвучка з обліком символів (main._say)."""
    parts = await asyncio.gather(*(say(x) for x in frags))
    out = []
    for data, _by in parts:
        if not data:
            return None, "missing"
        if data[:4] == b"RIFF":
            return None, "wav"
        out.append(_strip_id3(data))
    return b"".join(out), "kit"


_WARM = {"state": "idle", "done": 0, "total": 0}


async def warm(say, paid_ok) -> None:
    """Фоном озвучує весь словник (≈600 коротких фраз, ≈20 тис. символів, разово ≈$0,30), по одній, щоб не навантажувати."""
    v = vocabulary()
    _WARM.update(state="running", total=len(v), done=0)
    for x in v:
        if not paid_ok():
            _WARM["state"] = "paused:cap"
            return
        try:
            data, _by = await say(x)
            if not data:
                _WARM["state"] = "paused:no-voice"
                return
        except Exception as e:  # noqa: BLE001
            log.warning("warm: %s", e)
        _WARM["done"] += 1
        await asyncio.sleep(0.3)
    _WARM["state"] = "done"


def status() -> dict:
    return dict(_WARM)
