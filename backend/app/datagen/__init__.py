"""
datagen — deterministic synthetic Lucknow crime dataset for the Argus demo.

    from app.datagen import generate
    counts = generate(out_dir)      # writes 5 CSVs + ground_truth.json

Planted cases (see planted_*.py) give the demo a scripted story while the
background noise makes resolution and graph analytics non-trivial.
"""

from __future__ import annotations

import csv
import json
import pathlib

from app.datagen import background, planted_fraud, planted_other
from app.datagen.builder import Builder

TABLES = {"fir": "firs", "person": "persons", "cdr": "cdr",
          "bank_txn": "txns", "vehicle_reg": "vehicles"}


def build(seed: int = 26189) -> Builder:
    b = Builder(seed)
    planted_fraud.build(b)
    planted_other.build(b)
    background.build(b)
    b.finalise()
    return b


def generate(out_dir: pathlib.Path, seed: int = 26189) -> dict[str, int]:
    b = build(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for table, attr in TABLES.items():
        rows = getattr(b, attr)
        with open(out_dir / f"{table}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        counts[table] = len(rows)
    (out_dir / "ground_truth.json").write_text(
        json.dumps(b.gt, indent=2, ensure_ascii=False), encoding="utf-8")
    return counts
