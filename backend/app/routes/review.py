"""
routes/review.py — GET /review-queue, POST /review/{pair_id}
Human review queue for uncertain entity-resolution pairs (0.40 < score < 0.85).
"""

from __future__ import annotations

import pathlib
import sqlite3

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import ledger

router = APIRouter(tags=["review"])

_DB = pathlib.Path(__file__).resolve().parent.parent.parent / "argus.db"


class ReviewDecision(BaseModel):
    decision: str   # "accept" | "reject"
    actor: str = "analyst"
    notes: str = ""


@router.get("/review-queue")
def get_review_queue():
    """List all pairs pending human review (score between 0.40 and 0.85)."""
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    try:
        pairs = conn.execute(
            "SELECT rq.id, rq.id_a, rq.id_b, rq.score, rq.ts, "
            "       pa.name AS name_a, pa.role AS role_a, "
            "       pb.name AS name_b, pb.role AS role_b "
            "FROM review_queue rq "
            "LEFT JOIN person pa ON rq.id_a = pa.id "
            "LEFT JOIN person pb ON rq.id_b = pb.id "
            "ORDER BY rq.score DESC"
        ).fetchall()
        return {"queue": [dict(r) for r in pairs], "count": len(pairs)}
    finally:
        conn.close()


@router.post("/review/{pair_id}")
def submit_review(pair_id: int, body: ReviewDecision):
    """Accept or reject a review-queue pair.

    - accept  -> copies pair to golden_entities, removes from review_queue
    - reject  -> removes from review_queue only

    Every decision is written to the ledger.
    """
    if body.decision not in ("accept", "reject"):
        raise HTTPException(status_code=422, detail="decision must be 'accept' or 'reject'")

    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    try:
        pair = conn.execute(
            "SELECT * FROM review_queue WHERE id=?", (pair_id,)
        ).fetchone()
        if not pair:
            raise HTTPException(status_code=404, detail=f"Review pair {pair_id} not found")

        if body.decision == "accept":
            conn.execute(
                "INSERT INTO golden_entities(id_a, id_b, score, ts) VALUES(?,?,?,?)",
                (pair["id_a"], pair["id_b"], pair["score"], pair["ts"]),
            )

        conn.execute("DELETE FROM review_queue WHERE id=?", (pair_id,))
        conn.commit()
    finally:
        conn.close()

    lid = ledger.append(
        action="REVIEW_SUBMIT",
        payload={
            "pair_id": pair_id,
            "id_a": pair["id_a"],
            "id_b": pair["id_b"],
            "score": pair["score"],
            "decision": body.decision,
            "notes": body.notes,
        },
        actor=body.actor,
        db_path=_DB,
    )

    return {
        "pair_id": pair_id,
        "decision": body.decision,
        "ledger_id": lid,
    }
