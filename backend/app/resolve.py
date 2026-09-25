"""
resolve.py — Entity resolution: block -> score -> three-way gate -> golden records.

Resolution gate (CLAUDE.md / deck slide 2):
  score >= 0.85  -> auto-accept  (golden_entities, via='auto')
  score <= 0.40  -> auto-reject
  else           -> review_queue (a human decides)

Every scored pair is kept in `match_pairs` with its factor-level evidence so
the UI can explain *why* two records were (or were not) merged. Earlier
analyst decisions (`human_decisions`) are replayed on every re-run, so the
system never asks the same question twice.

VICTIM records never enter resolution (DPDP purpose limitation).
Scoring lives in er/score.py, blocking in er/blocking.py.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
from datetime import datetime, timezone

from app.er.blocking import candidate_pairs
from app.er.golden import ensure_tables, group_pairs, rebuild_masters
from app.er.normalise import surname_corpus
from app.er.score import ACCEPT, REJECT, score_breakdown, score_pair  # noqa: F401 (re-export)

_HERE = pathlib.Path(__file__).resolve().parent
DB_PATH = _HERE.parent / "argus.db"


def resolve_all(db_path: str | pathlib.Path = DB_PATH) -> dict:
    """Run full resolution over all Person rows. Returns pipeline statistics."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        ensure_tables(conn)
        for t in ("match_pairs", "golden_entities", "review_queue"):
            conn.execute(f"DELETE FROM {t}")

        everyone = [dict(r) for r in conn.execute("SELECT * FROM person")]
        persons = [p for p in everyone if p["role"] != "VICTIM"]
        by_id = {p["id"]: p for p in persons}
        corpus = surname_corpus([p["name"] for p in persons])
        human = {(r["id_a"], r["id_b"]): r["decision"]
                 for r in conn.execute("SELECT * FROM human_decisions")}

        pairs, stats = candidate_pairs(persons)
        ts = datetime.now(timezone.utc).isoformat()
        counts = {"accept": 0, "review": 0, "reject": 0, "human": 0}
        for a, b, keys in pairs:
            br = score_breakdown(by_id[a], by_id[b], corpus)
            decision = br["decision"]
            evidence = json.dumps(br, ensure_ascii=False)
            if (a, b) in human:                        # analyst already ruled on this pair
                decision = "human_" + human[(a, b)]
                counts["human"] += 1
            else:
                counts[decision] += 1
            conn.execute(
                "INSERT INTO match_pairs(id_a,id_b,score,decision,evidence_json,blocks_json,ts) "
                "VALUES (?,?,?,?,?,?,?)", (a, b, br["score"], decision, evidence, json.dumps(keys), ts))
            if decision in ("accept", "human_accept"):
                conn.execute("INSERT INTO golden_entities(id_a,id_b,score,ts,via) VALUES (?,?,?,?,?)",
                             (a, b, br["score"], ts, "human" if decision == "human_accept" else "auto"))
            elif decision == "review":
                conn.execute("INSERT INTO review_queue(id_a,id_b,score,ts,evidence_json) VALUES (?,?,?,?,?)",
                             (a, b, br["score"], ts, evidence))
        conn.commit()
        n_masters = rebuild_masters(conn)
        in_review = conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0]
        merged = conn.execute("SELECT COALESCE(SUM(n_records),0) FROM master_entity").fetchone()[0]
        return {
            **stats,
            "victims_excluded": len(everyone) - len(persons),
            "accepted": counts["accept"], "rejected": counts["reject"],
            "review": in_review, "transitive": counts["review"] - in_review,
            "human_replayed": counts["human"],
            "golden_records": n_masters, "records_merged": merged,
            "thresholds": {"accept": ACCEPT, "reject": REJECT},
        }
    finally:
        conn.close()


def record_human_decision(conn: sqlite3.Connection, id_a: str, id_b: str,
                          decision: str, actor: str) -> None:
    """Persist an analyst ruling (for every pair between the two entities) so
    future re-runs replay it."""
    ts = datetime.now(timezone.utc).isoformat()
    for a, b in group_pairs(conn, id_a, id_b) or [(id_a, id_b)]:
        conn.execute("INSERT OR REPLACE INTO human_decisions VALUES (?,?,?,?,?)",
                     (a, b, decision, actor, ts))
        conn.execute("UPDATE match_pairs SET decision=? WHERE id_a=? AND id_b=?",
                     ("human_" + decision, a, b))
    if decision == "accept":
        score = conn.execute("SELECT score FROM match_pairs WHERE id_a=? AND id_b=?",
                             (id_a, id_b)).fetchone()
        conn.execute("INSERT INTO golden_entities(id_a,id_b,score,ts,via) VALUES (?,?,?,?,'human')",
                     (id_a, id_b, score[0] if score else 0.0, ts))
    conn.execute("DELETE FROM review_queue WHERE id_a=? AND id_b=?", (id_a, id_b))
    conn.commit()
    rebuild_masters(conn)
