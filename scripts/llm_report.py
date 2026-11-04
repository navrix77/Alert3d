"""Звіт «другого парсера» для нічного розбору: де модель(і) не згодні з правилами і між собою.

    python scripts/llm_report.py [data/llm.jsonl] [--hours 24]

Порівнює тип і множину названих місць (правила vs модель vs друга модель). Згода двох незалежних моделей проти
правил — найкращий кандидат на виправлення правил (з тестом на реальному тексті)."""
from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def places(x: dict) -> set:
    from app.geo import phon
    return {phon(n)[:5] for n in (x.get("now") or []) + (x.get("to") or []) + (x.get("from") or [])}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=str(ROOT / "data" / "llm.jsonl"))
    ap.add_argument("--hours", type=float, default=24)
    a = ap.parse_args()
    from app.geo import phon
    rows = []
    for ln in Path(a.path).read_text(encoding="utf-8").splitlines() if Path(a.path).exists() else []:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if time.time() - r.get("t", 0) < a.hours * 3600:
            rows.append(r)
    st = collections.Counter()
    disagree, both = [], []
    for r in rows:
        st["n"] += 1
        st["why:" + r.get("why", "?").split(":")[0]] += 1
        rt = {x.get("type") for x in r.get("rules", []) if x.get("type")}
        rp = {phon(p[0])[:5] for x in r.get("rules", []) for p in x.get("places", [])}
        m = r.get("llm") or {}
        mt = m.get("type")
        mp = places(m)
        same_t = (not rt and mt in (None, "unknown")) or mt in rt
        same_p = bool(mp & rp) or (not mp and not rp)
        st["type_agree"] += same_t
        st["place_agree"] += same_p
        if "llm2" in r:
            m2 = r["llm2"]
            st["with_second"] += 1
            st["models_agree"] += (m2.get("type") == mt) and bool(places(m2) & mp or (not mp and not places(m2)))
            if m2.get("type") == mt and (not same_t or not same_p):
                both.append({"src": r["src"], "text": r["text"][:140], "rules": r.get("rules"), "llm": m, "by": [r.get("by"), r.get("by2")]})
        if not same_t or not same_p:
            disagree.append({"src": r["src"], "why": r.get("why"), "text": r["text"][:140], "rules": r.get("rules"), "llm": m})
    print(json.dumps({"stats": st, "two_models_against_rules": both[:30], "disagree": disagree[:40]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
