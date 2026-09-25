"""
er/blocking.py — Candidate generation so we never score all O(n^2) pairs.

A pair is only scored if the two records share a blocking key:
  * any strong identifier value (phone / IMEI / vehicle / account), or
  * a phonetic name key: first 3 letters of the first name + surname.

Every pair that can reach auto-accept shares a strong identifier, so it is
always blocked together. Weak-evidence-only pairs (max 0.50) need a very
similar name to enter review; the name key covers the realistic ones.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations

from app.er.normalise import phonetic
from app.er.score import STRONG


def _name_keys(p: dict) -> set[str]:
    keys = set()
    for raw in (p.get("name"), p.get("alias")):
        toks = phonetic(raw or "").split()
        if len(toks) >= 2:
            keys.add(f"name:{toks[0][:3]}|{toks[-1]}")
    return keys


def candidate_pairs(persons: list[dict]) -> tuple[list[tuple[str, str, list[str]]], dict]:
    """Return ([(id_a, id_b, [block keys]), ...], stats)."""
    blocks: dict[str, list[str]] = defaultdict(list)
    for p in persons:
        for field, _ in STRONG:
            v = (p.get(field) or "").strip()
            if v:
                blocks[f"{field}:{v}"].append(p["id"])
        for k in _name_keys(p):
            blocks[k].append(p["id"])

    pairs: dict[tuple[str, str], list[str]] = defaultdict(list)
    by_kind: dict[str, int] = defaultdict(int)
    for key, ids in blocks.items():
        for a, b in combinations(sorted(set(ids)), 2):
            if not pairs[(a, b)]:
                by_kind[key.split(":")[0]] += 1
            pairs[(a, b)].append(key)

    n = len(persons)
    stats = {"records": n, "possible_pairs": n * (n - 1) // 2,
             "candidate_pairs": len(pairs), "by_block": dict(by_kind),
             "blocks": sum(1 for ids in blocks.values() if len(set(ids)) > 1)}
    return [(a, b, keys) for (a, b), keys in sorted(pairs.items())], stats
