"""Українська озвучка на сервері — Piper (github.com/rhasspy/piper) з голосами rhasspy/piper-voices (uk_UA):
Лада, Микита, Тетяна, Олекса та багатоголосна ukrainian_tts. Звучить природно, без «покручених» слів системного голосу.

Перший запуск: якщо пакета piper-tts немає — сервер сам ставить його у своє оточення (pip) у фоні;
модель голосу завантажується з Hugging Face один раз і кешується в data/voices. Готові фрази теж кешуються."""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
import re
import subprocess
import time
import sys
import threading
import wave
from pathlib import Path

import httpx

log = logging.getLogger("tts")
BASE = Path(os.getenv("PERSIST_DIR") or Path(__file__).resolve().parent.parent / "data") / "voices"
HF = "https://huggingface.co/rhasspy/piper-voices"
VOICES = {  # ключ → (папка в piper-voices, ім'я диктора для багатоголосної моделі)
    "lada": ("lada", None), "mykyta": ("mykyta", None), "tetiana": ("tetiana", None), "oleksa": ("oleksa", None),
}
NAMES = {"lada": "Лада", "mykyta": "Микита", "tetiana": "Тетяна", "oleksa": "Олекса"}
_loaded: dict = {}
_lock = threading.Lock()
_install = {"state": "idle", "error": None}


def piper_ok() -> bool:
    try:
        import piper  # noqa: F401
    except Exception:
        return False
    try:  # рушій є, але словника наголосів ще немає — доставляємо у фоні (сервер уже працює зі старою вимовою)
        import ukrainian_word_stress  # noqa: F401
        import num2words  # noqa: F401
    except Exception:
        _install_bg()
    return True


def _install_bg():
    if _install["state"] in ("running", "done"):
        return
    _install["state"] = "running"

    def go():
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "piper-tts", "marisa-trie", "num2words"], check=True, timeout=900)
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--no-deps", "ukrainian-word-stress"], check=True, timeout=600)
            _install["state"] = "done"
            log.info("piper-tts встановлено")
        except Exception as e:  # noqa: BLE001
            _install["state"], _install["error"] = "failed", str(e)[:200]
            log.warning("piper-tts не встановився: %s", e)
    threading.Thread(target=go, daemon=True).start()


async def _ensure_model(key: str) -> Path | None:
    folder, _spk = VOICES.get(key, VOICES["lada"])
    d = BASE / folder
    have = sorted(d.glob("*.onnx"))
    if have and (have[0].with_suffix(".onnx.json")).exists():
        return have[0]
    d.mkdir(parents=True, exist_ok=True)
    # токен Hugging Face (якщо є в .env) — вищий ліміт завантажень, голоси качаються без відмов 429
    hf = (os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HF_TOKEN") or "").strip()
    async with httpx.AsyncClient(timeout=120, follow_redirects=True, headers={"Authorization": f"Bearer {hf}"} if hf else None) as cli:
        lst = (await cli.get(f"https://huggingface.co/api/models/rhasspy/piper-voices/tree/main/uk/uk_UA/{folder}")).json()
        quals = [x["path"].rsplit("/", 1)[-1] for x in lst if x.get("type") == "directory"]
        q = next((x for x in ("medium", "high", "low", "x_low") if x in quals), None)
        if not q:
            return None
        name = f"uk_UA-{folder}-{q}"
        for ext in (".onnx.json", ".onnx"):
            r = await cli.get(f"{HF}/resolve/main/uk/uk_UA/{folder}/{q}/{name}{ext}")
            r.raise_for_status()
            (d / f"{name}{ext}").write_bytes(r.content)
    return d / f"{name}.onnx"


def _voice(path: Path):
    with _lock:
        v = _loaded.get(path)
        if v is None:
            from piper import PiperVoice
            v = _loaded[path] = PiperVoice.load(str(path))
        return v


# ---- наголоси: espeak-ng ставить їх часто неправильно (ша́хед, ле́тить, хви́лин). Беремо словник наголосів
# lang-uk/ukrainian-word-stress (без важкого Stanza) + власні слова, і переносимо наголос у фонемах кожного слова.
OVERRIDE = {"шахед": "шахе́д", "шахеди": "шахе́ди", "шахедів": "шахе́дів", "шахедом": "шахе́дом", "герань": "гера́нь",
            "гербера": "ге́рбера", "молнія": "мо́лнія", "каб": "ка́б", "каби": "ка́би", "кабів": "ка́бів", "дрон": "дро́н",
            "дрони": "дро́ни", "безпілотник": "безпіло́тник", "fpv": "еф-пе-ве́", "рсзв": "ер-ес-зе-ве́", "харків": "ха́рків",
            "харкова": "ха́ркова", "курсом": "ку́рсом", "напрямку": "напря́мку", "тривога": "триво́га", "відбій": "відбі́й",
            "реактивний": "реакти́вний", "реактивні": "реакти́вні", "балістика": "балі́стика", "ракета": "раке́та"}
VOW = set("аеєиіїоуюя")
PH_VOW = set("aɛeɪiouɐʊəɔæ")
_stress = None


_stress_try = 0.0


def _stressifier():
    global _stress, _stress_try
    import time as _t
    if _stress is False and _t.time() - _stress_try > 120:
        _stress = None  # словник могли щойно доставити — пробуємо знову
    if _stress is None:
        _stress_try = _t.time()
        try:
            from ukrainian_word_stress import OnAmbiguity, Stressifier, StressSymbol
            _stress = Stressifier(stress_symbol=StressSymbol.CombiningAcuteAccent, on_ambiguity=OnAmbiguity.First,
                                  disambiguation="dictionary")
        except Exception as e:  # noqa: BLE001
            log.info("словник наголосів недоступний: %s", e)
            _stress = False
    return _stress


def normalize(text: str) -> str:
    import re as _re
    t = text.replace("~", " приблизно ").replace("≈", " приблизно ").replace("×", " ").replace("·", ",").replace("→", " курсом на ")
    t = _re.sub(r"(\d+)\s*км\b", r"\1 кілометрів", t)
    t = _re.sub(r"(\d+)\s*хв\b", r"\1 хвилин", t)
    t = _re.sub(r"\bобл\.", "області", t)
    for a, b in (("БпЛА", "безпілотник"), ("БПЛА", "безпілотник"), ("бпла", "безпілотник"), ("р-н", "район"), ("FPV", "еф пе ве"),
                 ("КАБи", "каби"), ("РСЗВ", "ер ес зе ве"), ("ППО", "пе пе о"), ("РФ", "ер еф"), ("ЗСУ", "зе ес у")):
        t = _re.sub(rf"(?<![\w]){_re.escape(a)}(?![\w])", b, t)
    try:
        from num2words import num2words
        t = _re.sub(r"\d+", lambda m: num2words(int(m.group()), lang="uk"), t)
    except Exception:
        pass
    return " ".join(t.split())


def stressed_index(word: str) -> int | None:
    """Номер наголошеного голосного (0..) у слові або None."""
    low = word.lower()
    w = OVERRIDE.get(low)
    if w is None:
        st = _stressifier()
        w = st(word) if st else word
    if "\u0301" not in w:
        return None
    k = -1
    for ch in w:
        if ch.lower() in VOW:
            k += 1
        elif ch == "\u0301":
            return max(k, 0)
    return None


def word_phonemes(ph_engine, word: str) -> list[str]:
    out = [p for sent in ph_engine.phonemize("uk", word) for p in sent]
    k = stressed_index(word)
    vowels = [i for i, p in enumerate(out) if p in PH_VOW]
    if k is None or k >= len(vowels) or len(vowels) < 2:
        return out  # невідоме слово або один склад — як у espeak
    out = [p for p in out if p not in ("ˈ", "ˌ")]
    vowels = [i for i, p in enumerate(out) if p in PH_VOW]
    out.insert(vowels[k], "ˈ")
    return out


def phonemize_text(text: str) -> list[list[str]]:
    import re as _re
    from piper.phonemize_espeak import EspeakPhonemizer
    eng = getattr(phonemize_text, "eng", None) or EspeakPhonemizer()
    phonemize_text.eng = eng
    sents, cur = [], []
    for tok in _re.findall(r"[\w'’ʼ\-]+|[.,!?;:]", normalize(text)):
        if _re.match(r"[.,!?;:]", tok):
            cur.append(tok)
            if tok in ".!?":
                sents.append(cur)
                cur = []
            else:
                cur.append(" ")
            continue
        if cur and cur[-1] != " ":
            cur.append(" ")
        cur += word_phonemes(eng, tok)
    if cur:
        sents.append(cur)
    return [s_ for s_ in sents if any(p.strip() for p in s_)]


def _synth(path: Path, text: str, rate: float) -> bytes:
    import numpy as np
    from piper.config import SynthesisConfig
    v = _voice(path)
    cfg = SynthesisConfig(length_scale=max(0.6, min(1.6, 1 / max(0.5, rate))))
    chunks = []
    try:
        for ph in phonemize_text(text):
            ph = [p for p in ph if p in v.config.phoneme_id_map]
            audio = v.phoneme_ids_to_audio(v.phonemes_to_ids(ph), cfg)
            if isinstance(audio, tuple):
                audio = audio[0]
            m = float(np.max(np.abs(audio))) or 1.0
            chunks.append(np.clip(audio / m, -1, 1))
            chunks.append(np.zeros(int(v.config.sample_rate * 0.18), dtype=np.float32))
        pcm = (np.concatenate(chunks) * 32767).astype(np.int16).tobytes()
    except Exception as e:  # noqa: BLE001 — запасний шлях: стандартна вимова Piper
        log.warning("наголоси: %s — без корекції", e)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            v.synthesize_wav(normalize(text), w, syn_config=cfg)
        return buf.getvalue()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(v.config.sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


# ---- Google Cloud Text-to-Speech (якщо задано GOOGLE_TTS_KEY): нейромережеві голоси uk-UA з правильними наголосами.
GKEY = os.getenv("GOOGLE_TTS_KEY") or os.getenv("GOOGLE_TILES_KEY_TTS") or ""
_gvoices: dict = {}


async def _google_voices() -> dict:
    """Найкращі доступні голоси uk-UA: Chirp3-HD > Neural2 > Wavenet > Standard, окремо жіночий і чоловічий."""
    if _gvoices or not GKEY:
        return _gvoices
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.get("https://texttospeech.googleapis.com/v1/voices", params={"languageCode": "uk-UA", "key": GKEY})
        r.raise_for_status()
        rank = lambda n: next((i for i, k in enumerate(("Chirp3-HD", "Chirp-HD", "Neural2", "Wavenet", "Standard")) if k in n), 9)
        vs = sorted(r.json().get("voices", []), key=lambda v: rank(v["name"]))
        for v in vs:
            g = v.get("ssmlGender", "").lower()
            _gvoices.setdefault("female" if g == "female" else "male" if g == "male" else "any", v["name"])
    return _gvoices


async def _google(text: str, key: str, rate: float) -> bytes | None:
    vs = await _google_voices()
    want = "male" if key in ("mykyta", "oleksa") else "female"
    name = vs.get(want) or vs.get("female") or vs.get("any") or vs.get("male")
    if not name:
        return None
    import base64
    async with httpx.AsyncClient(timeout=20) as cli:
        r = await cli.post("https://texttospeech.googleapis.com/v1/text:synthesize", params={"key": GKEY},
                           json={"input": {"text": text}, "voice": {"languageCode": "uk-UA", "name": name},
                                 "audioConfig": {"audioEncoding": "MP3", "speakingRate": max(0.7, min(1.4, rate))}})
        r.raise_for_status()
        return base64.b64decode(r.json()["audioContent"])


# Природний голос із правильними наголосами (власник 03.11: «голос жахливий, наголоси не ті»): нейромережевий TTS OpenAI,
# якщо є OPENAI_API_KEY. Голос і манеру можна змінити в .env: TTS_OPENAI_MODEL, TTS_OPENAI_VOICE. Piper лишається запасним.
LAST = {"openai": "", "gemini": ""}  # остання помилка OpenAI TTS (без ключа) — для /api/tts/check
VOICE_V = "r2"  # змінюється разом із голосами/інструкцією — старий кеш озвучки не використовується
OAI_VOICES = {"lada": "coral", "tetiana": "sage", "mykyta": "ash", "oleksa": "onyx"}
# 04.11 власник: «голос і вимова — погано». Детальна інструкція диктора: рідна українська, радійна подача, наголоси назв
OAI_STYLE = ("Ти диктор українського інформаційного радіо. Говори рідною українською без російського акценту, природно і впевнено, "
             "як ведучий новин уночі: спокійний теплий тон, помірний темп, коротка пауза після кожного речення, без драматизму і без "
             "співучості. Числа читай природно. Наголоси як у літературній українській: Харків, Чугуїв, Балаклія, Ізюм, Лозова, "
             "Куп'янськ, Мерефа, Дергачі, Золочів, Богодухів, Красноград, Полтава, Кременчук, Кропивницький, Олександрія, Суми, "
             "Охтирка, Миргород, Дніпро, Павлоград, Запоріжжя, Чернігів, Київ, Біла Церква, Вінниця, Одеса, Миколаїв.")


async def _openai(text: str, key: str, rate: float) -> bytes | None:
    k = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not k:
        return None
    voice = os.getenv("TTS_OPENAI_VOICE") or OAI_VOICES.get(key, "nova")
    async with httpx.AsyncClient(timeout=30) as cli:
        for model in (os.getenv("TTS_OPENAI_MODEL") or "gpt-4o-mini-tts", "tts-1-hd"):
            body = {"model": model, "voice": voice, "input": text, "response_format": "mp3", "speed": max(0.8, min(1.3, rate * 0.97))}
            if model.startswith("gpt-"):
                body["instructions"] = OAI_STYLE
            r = await cli.post("https://api.openai.com/v1/audio/speech", json=body, headers={"Authorization": f"Bearer {k}"})
            if r.status_code == 200 and r.content:
                return r.content
            LAST["openai"] = f"{model}: HTTP {r.status_code} {r.text[:160]}"
            log.warning("openai tts %s: %s", model, r.status_code)
            if r.status_code in (401, 429) and any(w in r.text for w in ("credit", "quota", "billing")):
                _off["openai"] = time.time() + 1800  # немає кредитів — не гаємо час щоразу
                return None
    return None


# Gemini TTS (ключ GEMINI_API_KEY): нейромережевий голос, добре читає українські назви. 03.11: OpenAI без кредитів (429).
GEM_VOICES = {"lada": "Kore", "tetiana": "Aoede", "mykyta": "Charon", "oleksa": "Orus"}
GEM_STYLE = "Прочитай українською спокійно й чітко, як диктор новин, з правильними наголосами в назвах міст і сіл: "
_off: dict = {}  # провайдер → до якого часу не пробувати (немає кредитів / ліміт)


def _gkey() -> str:
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI") or os.getenv("GOOGLE_API_KEY") or "").strip()


def _wav(pcm: bytes, sr: int = 24000) -> bytes:
    import struct
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


async def _gemini(text: str, key: str, rate: float) -> bytes | None:
    import base64
    k = _gkey()
    if not k:
        return None
    voice = os.getenv("TTS_GEMINI_VOICE") or GEM_VOICES.get(key, "Kore")
    pre = GEM_STYLE + ("трохи швидше: " if rate > 1.1 else "")
    async with httpx.AsyncClient(timeout=40) as cli:
        for model in [m for m in (os.getenv("TTS_GEMINI_MODEL"), "gemini-2.5-flash-preview-tts", "gemini-2.5-flash-tts",
                                  "gemini-2.5-pro-preview-tts") if m]:
            r = await cli.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                               headers={"x-goog-api-key": k},
                               json={"contents": [{"parts": [{"text": pre + text}]}],
                                     "generationConfig": {"responseModalities": ["AUDIO"],
                                                          "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}})
            if r.status_code == 200:
                try:
                    part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
                except (KeyError, IndexError, ValueError):
                    LAST["gemini"] = f"{model}: порожня відповідь"
                    continue
                m = re.search(r"rate=(\d+)", part.get("mimeType", ""))
                return _wav(base64.b64decode(part["data"]), int(m.group(1)) if m else 24000)
            LAST["gemini"] = f"{model}: HTTP {r.status_code} {r.text[:160]}"
            log.warning("gemini tts %s: %s", model, r.status_code)
            if r.status_code == 429:
                _off["gemini"] = time.time() + 600
                return None
    return None


async def _cached(prov: str, ext: str, fn, text: str, key: str, rate: float):
    c = BASE / "cache" / f"{prov[0]}-{hashlib.sha1(f'{VOICE_V}|{key}|{rate}|{text}'.encode()).hexdigest()}.{ext}"
    if c.exists():
        return c.read_bytes(), f"{prov}-cache"
    if _off.get(prov, 0) > time.time():
        return None, ""
    try:
        data = await fn(text, key, rate)
    except Exception as e:  # noqa: BLE001
        LAST[prov] = f"{type(e).__name__}: {str(e)[:160]}"
        log.warning("%s tts: %s", prov, e)
        return None, ""
    if data:
        c.parent.mkdir(parents=True, exist_ok=True)
        c.write_bytes(data)
        return data, prov
    return None, ""


# Словник вимови: на екрані скорочення, у голосі — як кажуть люди (порада власника 03.11)
SAY = [(r"МіГ-?31\s?К", "міг тридцять один ка"), (r"МіГ-?31\s?І", "міг тридцять один і"), (r"МіГ-?31", "міг тридцять один"),
       (r"Ту-?95\s?МС", "ту дев'яносто п'ять ем ес"), (r"Ту-?95", "ту дев'яносто п'ять"), (r"Ту-?160", "ту сто шістдесят"),
       (r"Ту-?22\s?М3", "ту двадцять два ем три"), (r"Су-?34", "су тридцять чотири"), (r"Су-?35", "су тридцять п'ять"),
       (r"Х-?101", "ха сто один"), (r"Х-?555", "ха п'ятсот п'ятдесят п'ять"), (r"Х-?22", "ха двадцять два"), (r"Х-?32", "ха тридцять два"),
       (r"Х-?59", "ха п'ятдесят дев'ять"), (r"Х-?69", "ха шістдесят дев'ять"), (r"Х-?31П?", "ха тридцять один"),
       (r"Іскандер-?М", "іскандер ем"), (r"Іскандер-?К", "іскандер ка"), (r"КН-?23", "ка ен двадцять три"), (r"С-?300", "ес триста"),
       (r"С-?400", "ес чотириста"), (r"БпЛА|БПЛА|бпла", "безпілотник"), (r"КАБ(?:и|ів)?", "каби"), (r"UPD|Upd|upd", "уточнення"),
       (r"р-н", "район"), (r"обл\.", "області"), (r"ТГ", "громада"), (r"FPV", "еф пе ве"), (r"ППО", "пе пе о"), (r"РФ", "росія")]


def say_form(text: str) -> str:
    t = re.sub(r"[×x](\d+)\b", r"\1", text).replace("→", " у напрямку ").replace("~", "приблизно ").replace("≈", "приблизно ")
    for a, b in SAY:
        t = re.sub(rf"(?<![\w-]){a}(?![\w])", b, t)
    return t


async def speak(text: str, key: str = "lada", rate: float = 1.0, paid: bool = True) -> tuple[bytes | None, str]:
    text = say_form(" ".join((text or "").split())[:300])
    if not text:
        return None, "empty"
    order = (os.getenv("TTS_ORDER") or "openai,gemini").split(",") if paid else []
    if not paid:  # денний ліміт платного голосу вичерпано: уже синтезоване з кешу, нове — запасним голосом
        for prov, ext in (("openai", "mp3"), ("gemini", "wav")):
            c = BASE / "cache" / f"{prov[0]}-{hashlib.sha1(f'{VOICE_V}|{key}|{rate}|{text}'.encode()).hexdigest()}.{ext}"
            if c.exists():
                return c.read_bytes(), f"{prov}-cache"
    for prov in order:
        prov = prov.strip()
        if prov == "openai" and os.getenv("OPENAI_API_KEY"):
            data, by = await _cached("openai", "mp3", _openai, text, key, rate)
        elif prov == "gemini" and _gkey():
            data, by = await _cached("gemini", "wav", _gemini, text, key, rate)
        else:
            continue
        if data:
            return data, by
    if GKEY:
        gcache = BASE / "cache" / f"g-{hashlib.sha1(f'{VOICE_V}|{key}|{rate}|{text}'.encode()).hexdigest()}.mp3"
        if gcache.exists():
            return gcache.read_bytes(), "google-cache"
        try:
            data = await _google(normalize(text), key, rate)
            if data:
                gcache.parent.mkdir(parents=True, exist_ok=True)
                gcache.write_bytes(data)
                return data, "google"
        except Exception as e:  # noqa: BLE001 — недоступний Google → локальний Piper
            log.warning("google tts: %s", e)
    if not piper_ok():
        _install_bg()
        return None, "installing" if _install["state"] == "running" else f"no-piper:{_install['state']}"
    cache = BASE / "cache" / f"{hashlib.sha1(f'v2|{bool(_stressifier())}|{key}|{rate}|{text}'.encode()).hexdigest()}.wav"
    if cache.exists():
        return cache.read_bytes(), "cache"
    try:
        path = await _ensure_model(key)
        if not path:
            return None, "no-model"
        data = await asyncio.to_thread(_synth, path, text, rate)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
        return data, "ok"
    except Exception as e:  # noqa: BLE001
        log.warning("tts: %s", e)
        return None, f"error:{str(e)[:120]}"


def status() -> dict:
    return {"openai": bool(os.getenv("OPENAI_API_KEY")), "openai_error": LAST["openai"], "gemini": bool(_gkey()), "gemini_error": LAST["gemini"], "google": bool(GKEY), "google_voices": _gvoices, "piper": piper_ok(), "install": _install, "voices": [{"key": k, "name": NAMES[k],
            "ready": bool(list((BASE / VOICES[k][0]).glob('*.onnx')))} for k in VOICES]}
