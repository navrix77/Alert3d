"""Налаштування з оточення (Cloud Run: змінні та Secret Manager)."""
from __future__ import annotations

import os
from pathlib import Path

# локальні секрети (ключі API) — у файлі .env поруч із застосунком; він не потрапляє в git
_ENV = Path(__file__).resolve().parent.parent / ".env"
if _ENV.exists():
    for _ln in _ENV.read_text(encoding="utf-8-sig").splitlines():
        _ln = _ln.strip()
        if _ln and not _ln.startswith("#") and "=" in _ln:
            _k, _v = _ln.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from .tracker import Source

TG_API_ID = int(os.getenv("TG_API_ID", "0") or 0)
TG_API_HASH = os.getenv("TG_API_HASH", "")
TG_SESSION = os.getenv("TG_SESSION", "")  # StringSession, створюється scripts/telegram_login.py
ALERTS_TOKEN = os.getenv("ALERTS_IN_UA_TOKEN", "")  # https://alerts.in.ua/api-request
UKRAINEALARM_KEY = os.getenv("UKRAINEALARM_API_KEY", "")  # https://api.ukrainealarm.com (ключ — через форму на сайті)
ALERTS_POLL_SEC = int(os.getenv("ALERTS_POLL_SEC", "15"))
PUSH_SEC = float(os.getenv("PUSH_SEC", "2"))
TG_WEB_CYCLE_SEC = float(os.getenv("TG_WEB_CYCLE_SEC", "5"))  # цикл: головні канали щоразу, решта — порціями по 30
MAP_STYLE_VECTOR = os.getenv("MAP_STYLE_VECTOR", "https://tiles.openfreemap.org/styles/liberty")
MAPTILER_KEY = os.getenv("MAPTILER_KEY", "")
# Google Map Tiles API (Photorealistic 3D Tiles) — ключ обмежте за HTTP-referrer у Google Cloud Console
GOOGLE_TILES_KEY = os.getenv("GOOGLE_TILES_KEY", "")

# Вайтлист каналів: ключ -> (username, назва, апріорна довіра, офіційний)
# (ключ, username, назва, довіра, офіційний, область-контекст, швидкий)
# швидкий=True — опитується кожен цикл (~12 с), решта — по черзі (~1–2 хв)
_C = [
    ("K", "kpszsu", "Повітряні Сили ЗСУ", 0.95, True, None, True),
    ("D", "Nablydatel_Dozor", "Наблюдатель · Ночной Дозор", 0.80, False, "Харківська", True),
    ("M", "monitor1654", "monitor 1654", 0.80, False, "Харківська", True),
    ("R", "radar_kharkov", "Радар Харків", 0.80, False, "Харківська", True),
    ("TRK", "tryvoga_rakety", "Радар Ракета | Шахеди", 0.55, False, None, True),
    ("TLK", "tlknewsua", "TLK News Харків", 0.88, False, "Харківська", True),
    # пріоритет для Харкова (03.11, Андрій): опитуються щоцикла; довіра стартова — далі її вчить журнал
    ("KHN", "KharkovNews2023", "KHARKOV-News", 0.60, False, "Харківська", True),
    ("KHL", "kharkivlife", "Kharkiv Life", 0.60, False, "Харківська", True),
    ("KM", "kharkov_media", "Харьков INFO", 0.75, False, "Харківська", True),
    ("ND", "NochnojDozorKh", "Ночной Дозор Харків", 0.75, False, "Харківська", True),
    ("CX", "cxidua", "СХІD", 0.65, False, "Харківська", True),
    ("SG", "synegubov", "Синєгубов (Харківська ОВА)", 0.90, True, "Харківська", True),
    ("KLB", "vitaliy_klitschko", "Кличко (мер Києва)", 0.85, True, "Київська", False),
    ("KMDA", "KyivCityOfficial", "КМДА", 0.85, True, "Київська", False),
    ("KOVA", "kyivoda", "Київська ОВА", 0.85, True, "Київська", False),
    ("SEN", "senkevichonline", "Сєнкевич (мер Миколаєва)", 0.85, True, "Миколаївська", False),
    ("BEL", "belousov_andrei", "Білоусов (мер Кам’янського)", 0.85, True, "Дніпропетровська", False),
    ("SAD", "andriysadovyi", "Садовий (мер Львова)", 0.85, True, "Львівська", False),
    ("KOZ", "kozytskyy_maksym_official", "Козицький (Львівська ОВА)", 0.85, True, "Львівська", False),
    ("TAB", "cherkaskaODA", "Табурець (Черкаська ОВА)", 0.85, True, "Черкаська", False),
    ("ZOV", "zoda_gov_ua", "Запорізька ОВА", 0.85, True, "Запорізька", False),
    ("FED", "ivan_fedorov_zp", "Федоров (Запорізька ОВА)", 0.85, True, "Запорізька", False),
    ("SOV", "Sumy_news_ODA", "Сумська ОВА", 0.85, True, "Сумська", False),
    ("KHO", "khersonskaODA", "Херсонська ОВА", 0.85, True, "Херсонська", False),
    ("DOD", "DonetskaODA", "Донецька ОДА", 0.85, True, "Донецька", False),
    ("ODO", "odesaoda", "Одеська ОВА", 0.85, True, "Одеська", False),
    ("TRH", "ihor_terekhov", "Терехов (мер Харкова)", 0.90, True, "Харківська", True),
    ("ZAD", "zadorenko_v", "Задоренко (Дергачівська МВА)", 0.85, True, "Харківська", True),
    ("MIN", "GalinaMinaeva", "Мінаєва (мер Чугуєва)", 0.85, True, "Харківська", True),
    ("HK", "huyovy_kharkiv", "Хуйовий Харків", 0.65, False, "Харківська", True),
    ("HS", "hs_kharkiv", "HS Харків", 0.60, False, "Харківська", True),
    ("TXK", "truexakharkiv", "Труха Харків", 0.55, False, "Харківська", True),
    ("MU", "mon1tor_ua", "ППО радар", 0.75, False, None, True),
    ("KL", "kudy_letyt", "Куди летить", 0.70, False, None, True),
    ("MK", "monitor_ukr", "Моніторинг Україна", 0.65, False, None, True),
    ("SU", "sumy_monitor", "Суми монітор", 0.70, False, "Сумська", True),
    ("PL", "PoltavaRadar", "Полтава радар", 0.65, False, "Полтавська", True),
    ("DN", "dnipro_alerts", "Дніпро тривоги", 0.65, False, "Дніпропетровська", True),
    ("KR", "kramatorsk_radar", "Краматорськ радар", 0.65, False, "Донецька", True),
]
_SLOW = {
    None: "UkraineAlarmSignal alarmua tryvoga_chomu eRadarrua monikppy povitryanatrivogaaa radar_raketaa radar_top_ua raketa_trevoga UkraineRadar_24_7 rozvidkaneba Ukrainian_Intelligence war_monitor veselyy_pivden pivden_varta Shturval_media sectorv666 totallzrada vibuxaviasia deraketaua admiralbukhta newspn zahidnimonitoring monitoring_zaxid truexanewsua operativnoZSU novini_ukrtg suspilnenews tgsn_ua zahid_golovne_ua PpoUARadar",
    "Вінницька": "vinnradar ppo_vinnytsa vin_info_ppo",  # vinytsa_radar: веб-версія закрита (перевірено 01.11.2026)
    "Волинська": "lutsk_radar lutsk_info volynblog",
    "Житомирська": "zhytomyr_operativ zhitomirtrivoga Angry_Pol korostentoday",
    "Івано-Франківська": "ifalarm",
    "Київська": "truexakyiv kievreal1 kievinfo_kyiv kiev_levyy_bereg kyiv_golovne KyivCityOfficial ppo_kiev kyivradar kyiv_alarm kyev_radar kyiv_nebo kiev_nebo kyiv_airdef monitoring_kyiv shahedradar kievinform_ua1 nebo_raketa k_dvizh radar_ukr",
    "Кіровоградська": "krop_vanek kirovograd_official",
    "Львівська": "lviv_raketna rocket_danger_lviv",
    "Полтавська": "ppo_poltava poltava_alarm PoltavaRanger ppopoltavanightfighters kremen_sv region_poltava_syrena truexapoltava",
    "Рівненська": "mapa_novinyr truexarivne",
    "Сумська": "rdsprostir sumygo sumyregion krolevetsnews svessainfo",
    "Тернопільська": "ternopil_ternopol truexaternopil",
    "Хмельницька": "khmlv tviy_Khmelnytskyi truexaxmelnitskyy",
    "Черкаська": "cherkasy_monitor cherkasy_nebbo",
    "Чернігівська": "Northern_Sich_ukr PhantomChe RadarChernihiv ShahedChernihiv horizon_of_war_Official my_safety_Chernigiv taktychna_rukavuchkaa",
    "Чернівецька": "goodchernivtsi",
    "Дніпропетровська": "Radar_Dnipra dnipromonitor pavlograd_radar nikalert dnepr_nagladach shovnebi svoikr truexakrivojrog yevtushenko_e",
    "Донецька": "operatyvnyi_donbas",
    "Запорізька": "radar_zp eyes_everywhere_ua operatyvnohlep gnilayachereha info_zp zaborzp",
    "Миколаївська": "vanek_nikolaev korabely_media pivden_FPV",
    "Одеська": "radar_odesa odessa_inform odessa_knight odessaveter ReniHub temporis_odesa odessa_infonews xydessa_live",
    "Харківська": "Karkivw kharkivlife kharkov_media kuptg place_kharkiv tlknewsua",
    "Херсонська": "kherson_monitoring kherson_non_drone",
}
_NEWS = {"truexanewsua", "operativnoZSU", "novini_ukrtg", "suspilnenews", "tgsn_ua", "zahid_golovne_ua", "truexakyiv", "kievreal1", "kievinfo_kyiv", "kiev_levyy_bereg", "kyiv_golovne", "newspn", "kharkivlife", "kharkov_media", "place_kharkiv", "tlknewsua", "kievinform_ua1", "odessa_infonews", "xydessa_live",
         "lutsk_info", "volynblog", "korostentoday", "sumyregion", "krolevetsnews", "svessainfo", "info_zp", "zaborzp", "odessa_inform", "kuptg", "Karkivw",
         "svoikr", "truexakrivojrog", "kirovograd_official", "truexarivne", "truexapoltava"}
_seen = {u.lower() for _, u, *_ in _C}
for region, names in _SLOW.items():
    for u in names.split():
        if u.lower() in _seen:
            continue
        _seen.add(u.lower())
        _C.append((u, u, "@" + u, 0.40 if u in _NEWS else 0.60, u == "KyivCityOfficial", region, False))
CHANNELS = [(k, u, n, r, off) for k, u, n, r, off, _reg, _f in _C]
CHANNEL_REGION = {k: reg for k, _u, _n, _r, _o, reg, _f in _C if reg}
FAST = {k for k, *_rest, f in _C if f}
extra = os.getenv("TG_CHANNELS_EXTRA", "")  # "key:username:Назва:0.7,..."
for item in filter(None, extra.split(",")):
    k, u, n, r = item.split(":")
    CHANNELS.append((k, u, n, float(r), False))

SOURCES = {k: Source(k, n, r, off, f"https://t.me/{u}") for k, u, n, r, off in CHANNELS}
SOURCES["AIU"] = Source("AIU", "Повітряні сили / alerts.in.ua", 0.92, True, "https://alerts.in.ua")
BY_USERNAME = {u.lower(): k for k, u, *_ in CHANNELS}
