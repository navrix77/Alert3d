"""Збирає газетир з OpenStreetMap (Overpass): українські та російські назви населених пунктів
України й прикордоння. Запускається під час збірки Docker-образу; якщо Overpass недоступний,
застосунок працює на вбудованому КАТОТТГ (лише українські назви)."""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "gazetteer_osm.json"
Q = '[out:json][timeout:240];node["place"~"^(city|town|village)$"](44.2,22.0,53.0,41.5);out tags qt;'
MIRRORS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]


def main() -> int:
    data = urllib.parse.urlencode({"data": Q}).encode()
    for url in MIRRORS:
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "tryvoga-gazetteer/1.0"})
            with urllib.request.urlopen(req, timeout=300) as r:
                j = json.load(r)
            out = []
            for e in j["elements"]:
                t = e.get("tags", {})
                out.append({"n": t.get("name"), "uk": t.get("name:uk"), "ru": t.get("name:ru"), "lat": round(e["lat"], 4),
                            "lon": round(e["lon"], 4), "p": t.get("place"), "pop": int(t["population"]) if str(t.get("population", "")).isdigit() else 0})
            OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            print(f"gazetteer: {len(out)} places from {url}")
            return 0
        except Exception as ex:  # noqa: BLE001
            print(f"overpass {url} failed: {ex}", file=sys.stderr)
    print("gazetteer: Overpass недоступний, лишаємо КАТОТТГ", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
