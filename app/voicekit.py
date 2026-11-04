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


def side_dist(side: str, km: float) -> str:
    k = km_round(km)
    return f"{side}, за {num(k)} {plural(k, 'кілометр', 'кілометри', 'кілометрів')} від вас."


def eta(m: int) -> str:
    m = max(1, min(int(m), 90))
    return f"Орієнтовно {num(m, 'f')} {plural(m, 'хвилина', 'хвилини', 'хвилин')}."


def more(n: int) -> str:
    return f"Поруч ще {num(n, 'f')} {plural(n, 'ціль', 'цілі', 'цілей')}."


FIXED = ["Увага!", "Оновлення.", "Ви слухаєте Скай Радіо.", "Наближається.", "Рухається не до вас.", "Напрямок невідомий.",
         "Точне місце не назване.", "Повідомлення про загрозу балістики для вашої області. Будьте в укритті.",
         "Тривога в області триває.", "У вашому районі повітряна тривога.", "Поруч з вами цілей немає.", "Без змін.",
         "Добра новина: ціль віддаляється.", "Оновлення SKY тимчасово недоступні. Стежте за офіційними сповіщеннями."]
SIDES = ["на півночі", "на північному сході", "на сході", "на південному сході", "на півдні", "на південному заході", "на заході", "на північному заході"]


def vocabulary() -> list[str]:
    """Закритий словник заготовок: синтезується наперед, щоб перше ж оновлення звучало без очікування."""
    v = list(FIXED)
    for typ in ("shahed", "jet", "cruise", "ballistic", "kab"):
        v += [count_type(n, typ) for n in range(1, 21)]
    for typ in TYPES:
        if typ not in ("shahed", "jet", "cruise", "ballistic", "kab"):
            v += [count_type(n, typ) for n in (1, 2, 3)]
    kms = list(range(1, 11)) + list(range(15, 205, 5))
    v += [side_dist(s, k) for s in SIDES for k in kms]
    v += [eta(m) for m in range(1, 31)] + [more(n) for n in range(1, 11)]
    return v


def compose(f: dict, first: bool = False, greeted: bool = True) -> list[str]:
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
            out.append(side_dist(x["side"], x["named_km"]))
            out.append(f"Місце: {x['at']}.")
        else:
            out.append(side_dist(x["side"], x["km"]))
            out.append("Точне місце не назване.")
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
        out.append("Поруч з вами цілей немає.")
    return out


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
