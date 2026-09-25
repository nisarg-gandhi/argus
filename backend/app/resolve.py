"""
resolve.py — Entity resolution: deduplicate and link Person records.

Resolution gate (CLAUDE.md / deck slide 2):
  score >= 0.85  -> auto-accept  (write to golden_entities)
  score <= 0.40  -> auto-reject  (discard)
  else           -> push to review_queue

Scoring (max 1.0, capped):
  Matching strong identifier (phone/IMEI/vehicle/account): +0.60 each,
      but first match gives full 0.60; additional each add 0.10 up to 0.80
  Fuzzy name similarity via token_set_ratio, scaled by surname_weight: up to +0.25
  Matching location (address substring):                   +0.10

VICTIM-role persons are excluded from cross-case merging.

Split into < 150 lines per CLAUDE.md rule; scoring helpers live here,
DB I/O at the bottom.
"""

from __future__ import annotations

import json
import re
import sqlite3
import pathlib
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from typing import Any

from rapidfuzz import fuzz

# ── DB path (mirrors seed.py convention) ────────────────────────────────────
_HERE   = pathlib.Path(__file__).resolve().parent
DB_PATH = _HERE.parent / "argus.db"

# ── Common surnames to down-weight (populated from seed corpus) ───────────────
_COMMON_SURNAMES: set[str] = {
    "kumar", "singh", "devi", "khan", "sharma", "verma", "yadav",
    "gupta", "mishra", "pandey", "tiwari", "prasad", "lal", "ram",
    "kaur", "ali", "begum", "nair", "pillai", "reddy",
}

# ── Honorifics and relational markers to strip ───────────────────────────────
_HONOURIFICS = re.compile(
    r"\b(mr\.?|mrs\.?|ms\.?|dr\.?|shri|smt\.?|kumari|late)\b",
    re.IGNORECASE,
)
_RELATIONS = re.compile(
    r"\b(s/o|d/o|w/o|son\s+of|daughter\s+of|wife\s+of|r/o|c/o|alias|a\.k\.a\.?)\b",
    re.IGNORECASE,
)
# Expand dotted initials: "R.K." -> "RK" (fuzzy still matches well)
_INITIALS = re.compile(r"\b([A-Z])\.(\s*)")


# ════════════════════════════════════════════════════════════════════════════
#  NAME NORMALISATION
# ════════════════════════════════════════════════════════════════════════════

def normalise_name(raw: str) -> str:
    """Strip honorifics, relational markers, extra whitespace.

    'Rakesh s/o Mahesh Yadav'  ->  'Rakesh Mahesh Yadav'
    'Smt. Sunita Devi'         ->  'Sunita Devi'
    'R.K. Yadav'               ->  'RK Yadav'
    """
    name = raw
    name = _HONOURIFICS.sub(" ", name)
    name = _RELATIONS.sub(" ", name)
    name = _INITIALS.sub(r"\1 ", name)         # R.K. -> R K
    name = re.sub(r"[^a-zA-Z\s]", " ", name)  # drop punctuation
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name.title()


# ════════════════════════════════════════════════════════════════════════════
#  SURNAME WEIGHT
# ════════════════════════════════════════════════════════════════════════════

def surname_weight(name: str, corpus: list[str] | None = None) -> float:
    """Return a weight in (0, 1] for the surname component of *name*.

    Common surnames (from _COMMON_SURNAMES or corpus TF) get weight < 1,
    reducing their contribution to name similarity.
    """
    tokens = normalise_name(name).lower().split()
    if not tokens:
        return 1.0
    surname = tokens[-1]

    # Corpus-based frequency (optional refinement)
    if corpus:
        all_surnames = [normalise_name(n).lower().split()[-1] for n in corpus if n.strip()]
        counts = Counter(all_surnames)
        total  = max(sum(counts.values()), 1)
        freq   = counts.get(surname, 0) / total
        # Sigmoid-like penalty: common surname (>10% of corpus) -> weight 0.5
        if freq > 0.10:
            return 0.50
        if freq > 0.05:
            return 0.70

    if surname in _COMMON_SURNAMES:
        return 0.55
    return 1.0


# ════════════════════════════════════════════════════════════════════════════
#  PAIR SCORING
# ════════════════════════════════════════════════════════════════════════════

def score_pair(a: dict[str, Any], b: dict[str, Any],
               corpus_names: list[str] | None = None) -> float:
    """Score how likely Person dicts *a* and *b* are the same individual.

    Each dict must have keys: id, name, role, phone, address (may be None).
    Optional keys: vehicle, imei, account.

    Returns float in [0.0, 1.0].
    """
    score = 0.0

    # ── Strong identifier matching ────────────────────────────────────────────
    strong_match_count = 0

    def _match_ids(field_a: str | None, field_b: str | None) -> bool:
        return bool(field_a and field_b and field_a.strip() == field_b.strip())

    for field in ("phone", "vehicle", "imei", "account"):
        if _match_ids(a.get(field), b.get(field)):
            strong_match_count += 1

    if strong_match_count >= 1:
        score += 0.60
    if strong_match_count >= 2:
        score += 0.20  # second strong ID is near-conclusive (phone + vehicle etc.)
    if strong_match_count >= 3:
        score += 0.05  # third match (capped by min(1.0) below)

    # ── Name similarity (scaled by surname weight) ────────────────────────────
    na = normalise_name(a.get("name", ""))
    nb = normalise_name(b.get("name", ""))
    if na and nb:
        raw_sim  = fuzz.token_set_ratio(na, nb) / 100.0  # 0-1
        weight   = min(
            surname_weight(na, corpus_names),
            surname_weight(nb, corpus_names),
        )
        # name contributes at most 0.25, scaled by weight
        name_score = raw_sim * weight * 0.25
        score += name_score

    # ── Location match ────────────────────────────────────────────────────────
    addr_a = (a.get("address") or "").lower().strip()
    addr_b = (b.get("address") or "").lower().strip()
    if addr_a and addr_b:
        # Token overlap: at least 2 common meaningful tokens
        toks_a = set(t for t in re.split(r"\W+", addr_a) if len(t) > 3)
        toks_b = set(t for t in re.split(r"\W+", addr_b) if len(t) > 3)
        if toks_a & toks_b:
            score += 0.10

    return min(score, 1.0)


# ════════════════════════════════════════════════════════════════════════════
#  PUBLIC API  — resolve_all()
# ════════════════════════════════════════════════════════════════════════════

_ACCEPT_THRESHOLD = 0.85
_REJECT_THRESHOLD = 0.40


def resolve_all(db_path: str | pathlib.Path = DB_PATH) -> dict[str, int]:
    """Run full resolution over all Person rows in *db_path*.

    Writes results to `golden_entities` (merged clusters) and
    `review_queue` (uncertain pairs).

    Returns counts: {"accepted": n, "rejected": n, "review": n}
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        _ensure_output_tables(conn)
        # Clear previous run results
        conn.execute("DELETE FROM golden_entities")
        conn.execute("DELETE FROM review_queue")

        rows = conn.execute(
            "SELECT id, name, role, phone, address, notes FROM person"
        ).fetchall()
        persons = [dict(r) for r in rows]

        # Collect all names for corpus-level surname frequency
        corpus_names = [p["name"] for p in persons]

        # Extract vehicle from notes field (seeded in notes column)
        for p in persons:
            p["vehicle"] = _extract_vehicle_from_notes(p.get("notes") or "")

        counts = {"accepted": 0, "rejected": 0, "review": 0}
        ts = datetime.now(timezone.utc).isoformat()

        # Union-Find for cluster tracking
        parent = {p["id"]: p["id"] for p in persons}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            parent[find(x)] = find(y)

        for pa, pb in combinations(persons, 2):
            # VICTIM persons: skip cross-cluster matching
            if pa["role"] == "VICTIM" or pb["role"] == "VICTIM":
                continue

            s = score_pair(pa, pb, corpus_names)

            if s >= _ACCEPT_THRESHOLD:
                union(pa["id"], pb["id"])
                conn.execute(
                    "INSERT INTO golden_entities(id_a, id_b, score, ts) VALUES(?,?,?,?)",
                    (pa["id"], pb["id"], round(s, 4), ts),
                )
                counts["accepted"] += 1
            elif s > _REJECT_THRESHOLD:
                conn.execute(
                    "INSERT INTO review_queue(id_a, id_b, score, ts) VALUES(?,?,?,?)",
                    (pa["id"], pb["id"], round(s, 4), ts),
                )
                counts["review"] += 1
            else:
                counts["rejected"] += 1

        conn.commit()
        return counts
    finally:
        conn.close()


# ── Legacy function signature from stub (keep for router compatibility) ───────

def resolve_persons(candidates: list[dict]) -> list[dict]:
    """Compare candidate Person records and return resolution decisions.

    Each candidate: {"id": str, "name": str, "role": str, "phone": str, ...}
    Returns list of {"pair": (id_a, id_b), "score": float, "decision": str}
    """
    corpus = [c.get("name", "") for c in candidates]
    results = []
    for a, b in combinations(candidates, 2):
        s = score_pair(a, b, corpus)
        if s >= _ACCEPT_THRESHOLD:
            decision = "accept"
        elif s > _REJECT_THRESHOLD:
            decision = "review"
        else:
            decision = "reject"
        results.append({"pair": (a["id"], b["id"]), "score": round(s, 4), "decision": decision})
    return results


# ════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _ensure_output_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS golden_entities (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            id_a    TEXT NOT NULL,
            id_b    TEXT NOT NULL,
            score   REAL NOT NULL,
            ts      TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS review_queue (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            id_a    TEXT NOT NULL,
            id_b    TEXT NOT NULL,
            score   REAL NOT NULL,
            ts      TEXT NOT NULL
        );
    """)
    conn.commit()


# Match vehicle plate in raw text (no pre-stripping — avoids word-boundary loss)
_RE_VEH_NOTES = re.compile(
    r"(?<![A-Z0-9])([A-Z]{2}\d{1,2}[A-Z]{1,3}\d{1,4})(?![A-Z0-9])",
    re.IGNORECASE,
)

def _extract_vehicle_from_notes(notes: str) -> str | None:
    m = _RE_VEH_NOTES.search(notes)
    return m.group(1).upper().replace(" ", "").replace("-", "") if m else None
