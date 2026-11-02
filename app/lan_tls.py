"""HTTPS у домашній мережі для «Неба в камері»: телефон дає камеру й компас лише через https.

Самопідписаний сертифікат (створюється сам при першому запуску) і невеликий TLS-проксі 8443 → 8090
в тому самому процесі — працює і для сторінок, і для WebSocket. Нічого не виставляється в інтернет:
слухає лише локальну мережу, як і основний сервер.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import ipaddress
import logging
import socket
import ssl
from pathlib import Path

log = logging.getLogger("tls")
DIR = Path(__file__).resolve().parent.parent / "data" / "tls"
PORT = 8443


def lan_ips() -> list[str]:
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:  # noqa: BLE001
        pass
    return sorted(i for i in ips if not i.startswith(("127.", "169.254.")))


def ensure_cert() -> tuple[Path, Path] | None:
    crt, key, ipsf = DIR / "tryvoga.crt", DIR / "tryvoga.key", DIR / "ips.txt"
    now_ips = ",".join(lan_ips())
    # адреса ПК у мережі змінилась (інший роутер / DHCP) — старий сертифікат на нову IP не діє, перевипускаємо
    if crt.exists() and key.exists() and ipsf.exists() and ipsf.read_text() == now_ips:
        return crt, key
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID
    except ImportError:
        log.warning("немає пакета cryptography — https для телефона вимкнено")
        return None
    DIR.mkdir(parents=True, exist_ok=True)
    k = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Тривога (локальна мережа)")])
    alt = [x509.DNSName("localhost")] + [x509.IPAddress(ipaddress.ip_address(i)) for i in lan_ips() + ["127.0.0.1"]]
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(k.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=825)).add_extension(x509.SubjectAlternativeName(alt), critical=False)
            .sign(k, hashes.SHA256()))
    key.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    ipsf.write_text(now_ips)
    log.info("https-сертифікат для локальної мережі: %s", now_ips)
    return crt, key


async def _pipe(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
    try:
        while data := await r.read(65536):
            w.write(data)
            await w.drain()
    except Exception:  # noqa: BLE001
        pass
    finally:
        try:
            w.close()
        except Exception:  # noqa: BLE001
            pass


async def run(target_port: int = 8090) -> None:
    pair = ensure_cert()
    if not pair:
        return
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(str(pair[0]), str(pair[1]))

    async def handle(cr: asyncio.StreamReader, cw: asyncio.StreamWriter) -> None:
        try:
            ur, uw = await asyncio.open_connection("127.0.0.1", target_port)
        except Exception:  # noqa: BLE001
            cw.close()
            return
        await asyncio.gather(_pipe(cr, uw), _pipe(ur, cw))

    try:
        srv = await asyncio.start_server(handle, "0.0.0.0", PORT, ssl=ctx)
    except OSError as e:
        log.warning("https-порт %s зайнятий: %s", PORT, e)
        return
    log.info("https для телефона: %s", ", ".join(f"https://{i}:{PORT}" for i in lan_ips()))
    ips0 = lan_ips()
    async with srv:
        while True:  # ПК перейшов в іншу мережу — перевипускаємо сертифікат і перезапускаємо https без перезапуску сервера
            await asyncio.sleep(120)
            if lan_ips() != ips0:
                log.info("змінилась адреса в мережі: %s → %s", ips0, lan_ips())
                srv.close()
                await srv.wait_closed()
                return await run(target_port)
