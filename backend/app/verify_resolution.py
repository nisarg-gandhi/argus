"""
verify_resolution.py — Ground-truth acceptance test for entity resolution.

Ingests the demo case into a throwaway database, runs resolve_all() and checks
every planted case from data/demo_case/ground_truth.json:

    python -m app.verify_resolution          # exit code 0 = all pass
"""

from __future__ import annotations

import csv
import json
import pathlib
import sqlite3
import sys
import tempfile

from app.er.golden import master_map
from app.ingest import ingest_data
from app.resolve import resolve_all

DEMO = pathlib.Path(__file__).resolve().parent.parent / "data" / "demo_case"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    gt = json.loads((DEMO / "ground_truth.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "verify.db"
        ingest_data(db, {t: list(csv.DictReader(open(DEMO / f"{t}.csv", encoding="utf-8")))
                         for t in ("fir", "person", "cdr", "bank_txn", "vehicle_reg")})
        stats = resolve_all(db)
        conn = sqlite3.connect(str(db))
        try:
            mm = master_map(conn)
            queued = {frozenset(r) for r in conn.execute("SELECT id_a, id_b FROM review_queue")}
            decided = {frozenset(r[:2]): r[2] for r in conn.execute("SELECT id_a, id_b, decision FROM match_pairs")}
            scored = {x for pair in decided for x in pair}
        finally:
            conn.close()

    same = lambda a, b: a in mm and mm.get(a) == mm.get(b)  # noqa: E731
    checks = []
    for name, ids in gt["must_merge"].items():
        checks.append((f"auto-merge  {name} ({len(ids)} records)", all(same(ids[0], i) for i in ids)))
    for a, b in gt["must_not_merge"]:
        checks.append((f"no auto-merge  {a} / {b}", not same(a, b)))
    for r in gt["review"]:
        a, b = r["pair"]
        in_queue = frozenset((a, b)) in queued or decided.get(frozenset((a, b))) in ("review", "review_grouped")
        checks.append((f"sent to human review  {a} ~ {b} (truth: {r['truth']})", in_queue and not same(a, b)))
    checks.append(("victim records never scored", not (set(gt["victims_protected"]) & scored)))

    print(f"Resolution: {stats['records']} records, {stats['possible_pairs']} possible pairs -> "
          f"{stats['candidate_pairs']} compared after blocking; {stats['accepted']} auto-accepted, "
          f"{stats['review']} to review, {stats['rejected']} rejected, {stats['golden_records']} golden records\n")
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    failed = sum(not ok for _, ok in checks)
    print(f"\n{'ALL CHECKS PASSED' if not failed else f'{failed} CHECK(S) FAILED'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
