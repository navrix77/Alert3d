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
import subprocess
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
        return True
    except Exception:
        return False


def _install_bg():
    if _install["state"] in ("running", "done"):
        return
    _install["state"] = "running"

    def go():
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "piper-tts"], check=True, timeout=900)
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
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as cli:
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


def _synth(path: Path, text: str, rate: float) -> bytes:
    from piper.config import SynthesisConfig
    v = _voice(path)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        v.synthesize_wav(text, w, syn_config=SynthesisConfig(length_scale=max(0.6, min(1.6, 1 / max(0.5, rate)))))
    return buf.getvalue()


async def speak(text: str, key: str = "lada", rate: float = 1.0) -> tuple[bytes | None, str]:
    text = " ".join((text or "").split())[:300]
    if not text:
        return None, "empty"
    if not piper_ok():
        _install_bg()
        return None, "installing" if _install["state"] == "running" else f"no-piper:{_install['state']}"
    cache = BASE / "cache" / f"{hashlib.sha1(f'{key}|{rate}|{text}'.encode()).hexdigest()}.wav"
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
    return {"piper": piper_ok(), "install": _install, "voices": [{"key": k, "name": NAMES[k],
            "ready": bool(list((BASE / VOICES[k][0]).glob('*.onnx')))} for k in VOICES]}
