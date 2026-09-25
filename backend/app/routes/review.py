"""
routes/review.py — Human-in-the-loop resolution (the "Unclear: ask human"
branch of the deck's flow).

  GET  /review-queue        one question per pair of entities, with evidence
  POST /review/{pair_id}    accept / reject -> signed on the evidence chain,
                            replayed on every future re-run, alerts refreshed
"""

from __future__ import annotations

import json
import pathlib
import sqlite3

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import ledger
from app.er.golden import ensure_tables, master_map
from app.resolve import record_human_decision
from app.rules import run_alert_rules

router = APIRouter(tags=["review"])
_DB = pathlib.Path(__file__).resolve().parent.parent.parent / "argus.db"
_PERSON_COLS = "p.id, p.name, p.alias, p.father_name, p.age, p.role, p.address, p.phone, p.vehicle, " \
               "p.account_no, p.imei, p.notes, p.fir_id, f.station, f.date"


class ReviewDecision(BaseModel):
    decision: str            # "accept" | "reject"
    actor: str = "analyst"
    notes: str = ""


def _person(conn, pid: str) -> dict:
    return dict(conn.execute(f"SELECT {_PERSON_COLS} FROM person p JOIN fir f ON f.id=p.fir_id "
                             f"WHERE p.id=?", (pid,)).fetchone())


@router.get("/review-queue")
def get_review_queue():
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    try:
        ensure_tables(conn)
        mm = master_map(conn)
        masters = {r["master_id"]: dict(r) for r in conn.execute("SELECT master_id, canonical, n_records FROM master_entity")}
        out = []
        for r in conn.execute("SELECT * FROM review_queue ORDER BY score DESC").fetchall():
            a, b = _person(conn, r["id_a"]), _person(conn, r["id_b"])
            out.append({"id": r["id"], "score": r["score"], "evidence": json.loads(r["evidence_json"]),
                        "a": a, "b": b,
                        "a_golden": masters.get(mm.get(a["id"], "")), "b_golden": masters.get(mm.get(b["id"], ""))})
        return {"queue": out, "count": len(out)}
    finally:
        conn.close()


@router.post("/review/{pair_id}")
def submit_review(pair_id: int, body: ReviewDecision):
    if body.decision not in ("accept", "reject"):
        raise HTTPException(422, "decision must be 'accept' or 'reject'")
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    try:
        pair = conn.execute("SELECT * FROM review_queue WHERE id=?", (pair_id,)).fetchone()
        if not pair:
            raise HTTPException(404, f"Review pair {pair_id} not found")
        names = {r["id"]: r["name"] for r in conn.execute(
            "SELECT id, name FROM person WHERE id IN (?,?)", (pair["id_a"], pair["id_b"]))}
        factors = [f["label"] for f in json.loads(pair["evidence_json"]).get("factors", [])]
        record_human_decision(conn, pair["id_a"], pair["id_b"], body.decision, body.actor)
        master = master_map(conn).get(pair["id_a"])
    finally:
        conn.close()

    block = ledger.append_many([("REVIEW_DECISION", {
        "pair": [pair["id_a"], pair["id_b"]], "names": [names.get(pair["id_a"]), names.get(pair["id_b"])],
        "machine_score": pair["score"], "decision": body.decision, "evidence": factors,
        "notes": body.notes}, body.actor)])
    alerts = run_alert_rules(_DB)
    return {"pair_id": pair_id, "decision": body.decision, "master_id": master,
            "ledger_id": block["seqs"][0], "block": block, "alerts": len(alerts)}
