"""
seed.py — Regenerate the demo dataset and reset the working database.

    python -m app.seed --reset                 # regenerate CSVs, wipe argus.db
    python -m app.seed --reset --fresh-chain   # ...and start a brand-new evidence chain

The dataset is deterministic (datagen, seed 26189): ~150 FIRs across 8 Lucknow
police stations, ~280 people, ~1.8k call records, ~300 bank transactions,
~60 vehicles, with planted cases whose ground truth is written to
data/demo_case/ground_truth.json (checked by `python -m app.verify_resolution`).
argus.db starts empty so the demo can show upload -> process live; pass --load
to ingest immediately.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import shutil
import sqlite3
import sys

from app.chain import DATA_DIR as CHAIN_DIR
from app.datagen import generate
from app.ingest import create_schema, ingest_data, wipe

_HERE = pathlib.Path(__file__).resolve().parent
DB_PATH = _HERE.parent / "argus.db"
DEMO_DIR = _HERE.parent / "data" / "demo_case"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="regenerate demo CSVs and wipe argus.db")
    ap.add_argument("--fresh-chain", action="store_true", help="delete all evidence-chain nodes and keys")
    ap.add_argument("--load", action="store_true", help="also ingest the demo case into argus.db")
    args = ap.parse_args()

    if args.reset:
        counts = generate(DEMO_DIR)
        print(f"[seed] generated demo case in {DEMO_DIR}")
        for table, n in counts.items():
            print(f"         {table:<12} {n:>5} rows")
        conn = sqlite3.connect(str(DB_PATH))
        try:
            wipe(conn)
            create_schema(conn)
        finally:
            conn.close()
        print(f"[seed] wiped case data in {DB_PATH}")
    if args.fresh_chain:
        shutil.rmtree(CHAIN_DIR, ignore_errors=True)
        print(f"[seed] deleted evidence chain at {CHAIN_DIR} (a new genesis block is created on first use)")
    if args.load:
        data = {t: list(csv.DictReader(open(DEMO_DIR / f"{t}.csv", encoding="utf-8")))
                for t in ("fir", "person", "cdr", "bank_txn", "vehicle_reg")}
        print(f"[seed] ingested: {ingest_data(DB_PATH, data)}")

    gt = json.loads((DEMO_DIR / "ground_truth.json").read_text(encoding="utf-8"))
    print("\n[seed] planted ground truth:")
    for name, ids in gt["must_merge"].items():
        print(f"   MERGE     {name:<32} {', '.join(ids)}")
    for p in gt["review"]:
        print(f"   REVIEW    {p['pair'][0]} ~ {p['pair'][1]}   (truth: {p['truth']})")
    for a, b in gt["must_not_merge"]:
        print(f"   NO-MERGE  {a} vs {b}")
    print(f"   PROTECTED victim records {', '.join(gt['victims_protected'])}")
    if not (args.reset or args.fresh_chain or args.load):
        print("\n(nothing changed — pass --reset, --fresh-chain and/or --load)")


if __name__ == "__main__":
    main()
