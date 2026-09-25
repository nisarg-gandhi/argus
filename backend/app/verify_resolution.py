"""
verify_resolution.py — Ground-truth acceptance tests for resolve.py.

Checks the 4 seed ground truths and prints PASS/FAIL for each.
Run after seeding:

    python -X utf8 -m app.verify_resolution

Exit code 0 = all pass, 1 = at least one failure.
"""

from __future__ import annotations

import sys
import sqlite3
import pathlib
from app.resolve import resolve_all, score_pair, normalise_name

_HERE   = pathlib.Path(__file__).resolve().parent
DB_PATH = _HERE.parent / "argus.db"

# ── Ground-truth constants (must match seed.py) ───────────────────────────────
YADAV_PHONE   = "9812345678"
YADAV_VEHICLE = "UP14CQ5566"
YADAV_IDS     = {"P-001", "P-002", "P-003"}   # must all land in same cluster
SUNITA_IDS    = {"P-004", "P-005"}             # must NOT be in same cluster
VICTIM_ID     = "P-006"                        # must not appear in golden_entities


def _load_persons(conn: sqlite3.Connection) -> dict[str, dict]:
    rows = conn.execute("SELECT id, name, role, phone, address, notes FROM person").fetchall()
    return {r[0]: dict(zip(["id","name","role","phone","address","notes"], r)) for r in rows}


def _golden_pairs(conn: sqlite3.Connection) -> set[frozenset]:
    rows = conn.execute("SELECT id_a, id_b FROM golden_entities").fetchall()
    return {frozenset([r[0], r[1]]) for r in rows}


def _same_cluster(pairs: set[frozenset], ids: set[str]) -> bool:
    """Return True if all ids are transitively linked via pairs."""
    id_list = list(ids)
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    for pair in pairs:
        a, b = tuple(pair)
        if a in ids and b in ids:
            union(a, b)

    root = find(id_list[0])
    return all(find(i) == root for i in id_list)


def _any_pair_in_golden(pairs: set[frozenset], ids: set[str]) -> bool:
    return any(pair.issubset(ids) for pair in pairs)


def run_tests() -> int:
    """Run all ground-truth checks. Returns number of failures."""
    print("=" * 60)
    print("  ARGUS -- RESOLUTION GROUND-TRUTH VERIFICATION")
    print("=" * 60)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    try:
        # Run resolution (wipes previous results each time)
        print("\n[*] Running resolve_all() ...")
        counts = resolve_all(DB_PATH)
        print(f"    accepted={counts['accepted']}  review={counts['review']}  rejected={counts['rejected']}\n")

        persons = _load_persons(conn)
        pairs   = _golden_pairs(conn)
        failures = 0

        # ── GT-1: Yadav cluster must merge ───────────────────────────────────
        gt1_pass = _same_cluster(pairs, YADAV_IDS)
        _print_check(
            "GT-1  Yadav cluster merges (P-001 / P-002 / P-003)",
            gt1_pass,
        )
        if not gt1_pass:
            failures += 1
            # Show individual pair scores for debugging
            yadav_persons = [persons[i] for i in sorted(YADAV_IDS)]
            for i in range(len(yadav_persons)):
                for j in range(i+1, len(yadav_persons)):
                    pa, pb = yadav_persons[i], yadav_persons[j]
                    # Inject vehicle for scoring debug
                    pa2 = dict(pa); pa2["vehicle"] = YADAV_VEHICLE
                    pb2 = dict(pb); pb2["vehicle"] = YADAV_VEHICLE
                    s = score_pair(pa2, pb2)
                    print(f"       score({pa['id']}, {pb['id']}) = {s:.4f}  "
                          f"[{normalise_name(pa['name'])} <-> {normalise_name(pb['name'])}]")

        # ── GT-1c: Yadav cluster graph collapse ──────────────────────────────
        from app.graphstore import build_graph
        G = build_graph(DB_PATH)
        yadav_nodes_in_graph = [n for n in YADAV_IDS if n in G]
        gt1c_pass = len(yadav_nodes_in_graph) == 1
        _print_check(
            "GT-1c Yadav cluster collapses into one master node in graph",
            gt1c_pass,
        )
        if gt1c_pass:
            master = yadav_nodes_in_graph[0]
            aka_len = len(G.nodes[master].get("aka", []))
            print(f"       Master node {master} has {aka_len} aka names.")
        else:
            failures += 1
            print(f"       Nodes found: {yadav_nodes_in_graph}")

        # ── GT-2: Two Sunita Devis must NOT merge ────────────────────────────
        gt2_pass = not _any_pair_in_golden(pairs, SUNITA_IDS)
        _print_check(
            "GT-2  Sunita Devi split — P-004 & P-005 NOT merged",
            gt2_pass,
        )
        if not gt2_pass:
            failures += 1
            for pid in SUNITA_IDS:
                p = persons[pid]
                print(f"       {pid}: phone={p['phone']}  addr={p['address']}")

        # ── GT-3: VICTIM (Priya Verma P-006) not in golden_entities ─────────
        victim_in_golden = any(VICTIM_ID in pair for pair in pairs)
        gt3_pass = not victim_in_golden
        _print_check(
            "GT-4  Priya Verma (VICTIM, P-006) excluded from merges",
            gt3_pass,
        )
        if not gt3_pass:
            failures += 1
            print(f"       VICTIM appeared in golden_entities — check VICTIM exclusion logic")

        # ── GT-4: Score sanity — Yadav pairs ≥ 0.85 ─────────────────────────
        corpus = [p["name"] for p in persons.values()]
        yadav_scores = []
        for pid_a, pid_b in [("P-001","P-002"), ("P-001","P-003"), ("P-002","P-003")]:
            pa = dict(persons[pid_a]); pa["vehicle"] = YADAV_VEHICLE
            pb = dict(persons[pid_b]); pb["vehicle"] = YADAV_VEHICLE
            s = score_pair(pa, pb, corpus)
            yadav_scores.append((pid_a, pid_b, s))

        all_high = all(s >= 0.85 for _, _, s in yadav_scores)
        gt4_pass = all_high
        _print_check(
            "GT-1b Yadav pair scores all >= 0.85",
            gt4_pass,
        )
        for pid_a, pid_b, s in yadav_scores:
            status = "OK" if s >= 0.85 else "FAIL"
            print(f"       score({pid_a}, {pid_b}) = {s:.4f}  [{status}]")
        if not gt4_pass:
            failures += 1

        # ── GT-5: Sunita pair score ≤ 0.40 ───────────────────────────────────
        pa = dict(persons["P-004"])
        pb = dict(persons["P-005"])
        sunita_score = score_pair(pa, pb, corpus)
        gt5_pass = sunita_score <= 0.40
        _print_check(
            "GT-2b Sunita Devi pair score <= 0.40",
            gt5_pass,
        )
        print(f"       score(P-004, P-005) = {sunita_score:.4f}")
        if not gt5_pass:
            failures += 1

    finally:
        conn.close()

    print()
    print("=" * 60)
    if failures == 0:
        print("  ALL CHECKS PASSED")
    else:
        print(f"  {failures} CHECK(S) FAILED — fix resolve.py and re-run")
    print("=" * 60)
    print()
    return failures


def _print_check(label: str, passed: bool) -> None:
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}]  {label}")


if __name__ == "__main__":
    sys.exit(run_tests())
