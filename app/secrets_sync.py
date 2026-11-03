"""Ключі на сервер без SSH і без ручного редагування файлів (03.11).

Як це працює:
1. Сервер має власну пару ключів RSA (приватний лише на сервері, поза репозиторієм) і віддає ПУБЛІЧНИЙ на /api/admin/envkey.
2. Власник один раз додає на GitHub секрет SKY_ENV (вміст свого .env.local) і запускає дію «Ключі → сервер».
3. Дія бере публічний ключ сервера, шифрує SKY_ENV і кладе в репозиторій лише шифр secrets/env.enc.
4. Сервер під час оновлення (кожні 5 хв) бачить новий env.enc, розшифровує своїм приватним ключем і дописує змінні
   у свій .env (права 600). Відкритих ключів немає ні в репозиторії, ні в логах, ні в чаті.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("secrets")
ROOT = Path(__file__).resolve().parent.parent
ENC = ROOT / "secrets" / "env.enc"


def _key_path() -> Path:
    p = os.getenv("ENV_KEY_FILE")
    if p:
        return Path(p)
    up = ROOT.parent  # на VM: /opt/navryx (поза репозиторієм /opt/navryx/app)
    return (up / ".navryx_envkey.pem") if os.access(up, os.W_OK) else (ROOT / "data" / ".navryx_envkey.pem")


def env_file() -> Path:
    p = os.getenv("ENV_FILE")
    if p:
        return Path(p)
    return ROOT.parent / ".env" if (ROOT.parent / ".env").exists() else ROOT / ".env"


def _private():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    kp = _key_path()
    if kp.exists():
        return serialization.load_pem_private_key(kp.read_bytes(), password=None)
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    kp.parent.mkdir(parents=True, exist_ok=True)
    kp.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    os.chmod(kp, 0o600)
    return key


def public_pem() -> str:
    from cryptography.hazmat.primitives import serialization
    return _private().public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def encrypt(pub_pem: str, text: str) -> str:
    """Те саме, що робить дія GitHub (для тестів і ручного використання)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    pub = serialization.load_pem_public_key(pub_pem.encode())
    k, n = AESGCM.generate_key(bit_length=256), os.urandom(12)
    c = AESGCM(k).encrypt(n, text.encode(), None)
    ek = pub.encrypt(k, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    fp = hashlib.sha256(pub_pem.encode()).hexdigest()[:16]
    return json.dumps({"v": 1, "fp": fp, "k": base64.b64encode(ek).decode(), "n": base64.b64encode(n).decode(), "c": base64.b64encode(c).decode()})


def decrypt(blob: str) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    d = json.loads(blob)
    k = _private().decrypt(base64.b64decode(d["k"]), padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    return AESGCM(k).decrypt(base64.b64decode(d["n"]), base64.b64decode(d["c"]), None).decode()


def parse_env(text: str) -> dict[str, str]:
    out = {}
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip().strip('"').strip("'")
        if k == "groq":
            k = "GROQ_API_KEY"
        if k.replace("_", "").isalnum():
            out[k] = v
    return out


def merge(path: Path, new: dict[str, str]) -> list[str]:
    """Додає/оновлює змінні в .env, решту рядків не чіпає. Повертає назви змінених."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    changed, keep = [], []
    for ln in lines:
        k = ln.split("=", 1)[0].strip().removeprefix("export ").strip() if "=" in ln else None
        if k in new:
            continue
        keep.append(ln)
    old = parse_env("\n".join(lines))
    for k, v in new.items():
        keep.append(f"{k}={v}")
        if old.get(k) != v:
            changed.append(k)
    if new.get("ANTHROPIC_API_KEY") or any(k.endswith("_API_KEY") for k in new):
        if "LLM_MODE" not in old and "LLM_MODE" not in new:
            keep.append("LLM_MODE=shadow")
            changed.append("LLM_MODE")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(keep) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return changed


def apply_pending() -> list[str]:
    """Якщо в репозиторії новий secrets/env.enc для цього сервера — розшифрувати й дописати в .env та os.environ."""
    if not ENC.exists():
        return []
    blob = ENC.read_text(encoding="utf-8").strip()
    h = hashlib.sha256(blob.encode()).hexdigest()
    mark = _key_path().with_suffix(".applied")
    if mark.exists() and mark.read_text().strip() == h:
        return []
    try:
        fp = json.loads(blob).get("fp")
        if fp and fp != hashlib.sha256(public_pem().encode()).hexdigest()[:16]:
            log.warning("secrets/env.enc зашифровано не для цього сервера — пропускаю")
            return []
        new = parse_env(decrypt(blob))
    except Exception as e:  # noqa: BLE001
        log.warning("secrets/env.enc не розшифровано: %s", type(e).__name__)
        return []
    changed = merge(env_file(), new)
    for k, v in new.items():
        os.environ[k] = v
    mark.write_text(h)
    log.info("ключі з GitHub застосовано (лише назви): %s", ", ".join(sorted(new)))
    return changed
