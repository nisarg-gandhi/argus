"""
er/score.py — Explainable pairwise match scoring.

Strong identifiers dominate (CLAUDE.md): first shared phone/IMEI/vehicle/
account = +0.60, second +0.20, further +0.05 each. Weak evidence is layered
on top and can also count *against* a match:

  name / alias similarity   up to +0.25, scaled down for common surnames
  father/husband name       +0.10 same,  -0.15 clearly different
  locality                  +0.10 same locality
  age                       +0.05 within 2 yrs, -0.10 more than 8 yrs apart

Weak evidence alone tops out at 0.50, so without a strong identifier a pair
can at most reach the human review band — never auto-accept.
"""

from __future__ import annotations

from collections import Counter

from rapidfuzz import fuzz

from app.er.normalise import display_name, localities, phonetic, surname, surname_weight

ACCEPT, REJECT = 0.85, 0.40
STRONG = [("phone", "phone"), ("imei", "IMEI"), ("vehicle", "vehicle"), ("account_no", "bank account")]
_STRONG_PTS = [0.60, 0.20]


def decide(score: float) -> str:
    return "accept" if score >= ACCEPT else "reject" if score <= REJECT else "review"


def score_breakdown(a: dict, b: dict, corpus: Counter | None = None) -> dict:
    """Return {'score', 'decision', 'factors': [{kind, label, points}]}."""
    factors: list[dict] = []

    n_strong = 0
    for field, label in STRONG:
        va, vb = (a.get(field) or "").strip(), (b.get(field) or "").strip()
        if va and va == vb:
            pts = _STRONG_PTS[n_strong] if n_strong < len(_STRONG_PTS) else 0.05
            factors.append({"kind": "strong", "field": field, "points": pts,
                            "label": f"Same {label} {va}"})
            n_strong += 1

    sim, pair = _best_name_sim(a, b)
    if sim > 0:
        wa, wb = surname_weight(pair[0], corpus), surname_weight(pair[1], corpus)
        w = min(wa, wb)
        common = surname(pair[0] if wa <= wb else pair[1]).title()
        note = f" (x{w:.2f}: '{common}' is a common surname)" if w < 1 else ""
        factors.append({"kind": "name", "points": round(sim * w * 0.25, 4),
                        "label": f"Name '{pair[0]}' ~ '{pair[1]}' {sim:.0%} similar{note}"})

    fa, fb = phonetic(a.get("father_name") or ""), phonetic(b.get("father_name") or "")
    if fa and fb:
        rel = fuzz.token_set_ratio(fa, fb) / 100
        if rel >= 0.9:
            factors.append({"kind": "weak", "points": 0.10,
                            "label": f"Same father/husband name ({display_name(a['father_name'])})"})
        elif rel < 0.6:
            factors.append({"kind": "negative", "points": -0.15,
                            "label": f"Different father/husband ({display_name(a['father_name'])} vs "
                                     f"{display_name(b['father_name'])})"})

    la, lb = localities(a.get("address") or ""), localities(b.get("address") or "")
    common = la & lb
    if common:
        factors.append({"kind": "weak", "points": 0.10, "label": f"Same locality: {', '.join(sorted(common)).title()}"})

    try:
        gap = abs(int(a.get("age")) - int(b.get("age")))
        if gap <= 2:
            factors.append({"kind": "weak", "points": 0.05, "label": f"Age consistent ({a['age']} / {b['age']})"})
        elif gap > 8:
            factors.append({"kind": "negative", "points": -0.10, "label": f"Age gap {gap} years"})
    except (TypeError, ValueError):
        pass

    score = round(max(0.0, min(1.0, sum(f["points"] for f in factors))), 4)
    return {"score": score, "decision": decide(score), "factors": factors}


def score_pair(a: dict, b: dict, corpus: Counter | None = None) -> float:
    return score_breakdown(a, b, corpus)["score"]


def _best_name_sim(a: dict, b: dict) -> tuple[float, tuple[str, str]]:
    """Best similarity across name/alias combinations, on phonetic forms."""
    best, pair = 0.0, ("", "")
    for x in (a.get("name"), a.get("alias")):
        for y in (b.get("name"), b.get("alias")):
            px, py = phonetic(x or ""), phonetic(y or "")
            if px and py:
                s = fuzz.token_set_ratio(px, py) / 100
                if s > best:
                    best, pair = s, (display_name(x), display_name(y))
    return best, pair
