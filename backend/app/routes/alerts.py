"""
routes/alerts.py — GET /alerts, GET /alert/{id},
                   POST /alert/{id}/feedback,
                   GET /export/{alert_id}

Feedback: tp/fp/tn/fn buttons write a row to `feedback` table (no retraining).
Export: JSON evidence bundle with SHA-256 hash + BSA s.63(4)-style chain-of-custody.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import ledger

router = APIRouter(tags=["alerts"])

_DB = pathlib.Path(__file__).resolve().parent.parent.parent / "argus.db"


class FeedbackBody(BaseModel):
    verdict: str          # "tp" | "fp" | "tn" | "fn"
    actor: str = "analyst"
    notes: str = ""


# ── Ensure feedback table exists ──────────────────────────────────────────────

def _ensure_feedback(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id   INTEGER NOT NULL,
            verdict    TEXT NOT NULL CHECK(verdict IN ('tp','fp','tn','fn')),
            actor      TEXT NOT NULL,
            notes      TEXT,
            ts         TEXT NOT NULL
        )
    """)
    conn.commit()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/alerts")
def list_alerts():
    """Return all generated alerts ordered by confidence desc."""
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM alerts ORDER BY confidence DESC"
        ).fetchall()
        return {
            "alerts": [
                {**dict(r),
                 "entities": json.loads(r["entities_json"]),
                 "source_ids": json.loads(r["source_ids_json"])}
                for r in rows
            ],
            "count": len(rows),
        }
    finally:
        conn.close()


@router.get("/alert/{alert_id}")
def get_alert(alert_id: int):
    """Return a single alert by id."""
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
        return {**dict(row),
                "entities": json.loads(row["entities_json"]),
                "source_ids": json.loads(row["source_ids_json"])}
    finally:
        conn.close()


@router.post("/alert/{alert_id}/feedback")
def submit_feedback(alert_id: int, body: FeedbackBody):
    """Record TP/FP/TN/FN feedback. Writes a row to `feedback` + ledger."""
    if body.verdict not in ("tp", "fp", "tn", "fn"):
        raise HTTPException(status_code=422, detail="verdict must be tp/fp/tn/fn")

    conn = sqlite3.connect(str(_DB))
    try:
        _ensure_feedback(conn)
        alert = conn.execute("SELECT id FROM alerts WHERE id=?", (alert_id,)).fetchone()
        if not alert:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

        ts = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO feedback(alert_id, verdict, actor, notes, ts) VALUES(?,?,?,?,?)",
            (alert_id, body.verdict, body.actor, body.notes, ts),
        )
        conn.commit()
        feedback_id = cur.lastrowid
    finally:
        conn.close()

    lid = ledger.append(
        action="FEEDBACK",
        payload={"alert_id": alert_id, "verdict": body.verdict,
                 "actor": body.actor, "feedback_id": feedback_id},
        actor=body.actor,
        db_path=_DB,
    )
    return {"feedback_id": feedback_id, "verdict": body.verdict, "ledger_id": lid}


@router.get("/export/{alert_id}")
def export_evidence(alert_id: int):
    """Export a BSA s.63(4)-style evidence bundle for *alert_id*.

    Bundle includes:
      - alert details + source records
      - SHA-256 hash of the payload
      - chain-of-custody ledger tail (last 5 entries)
      - provenance metadata
    """
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
        alert = dict(row)
        entities   = json.loads(alert["entities_json"])
        source_ids = json.loads(alert["source_ids_json"])

        # Gather source records
        source_records: list[dict] = []
        for sid in source_ids:
            for tbl in ("fir", "cdr", "bank_txn"):
                r = conn.execute(f"SELECT * FROM {tbl} WHERE id=?", (sid,)).fetchone()
                if r:
                    source_records.append({"table": tbl, "record": dict(r)})

        # Ledger tail
        ledger_tail = conn.execute(
            "SELECT id, ts, actor, action, row_hash FROM ledger ORDER BY id DESC LIMIT 5"
        ).fetchall()

    finally:
        conn.close()

    bundle = {
        "bsa_section": "63(4)",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "alert": {**alert,
                  "entities": entities,
                  "source_ids": source_ids},
        "source_records": source_records,
        "chain_of_custody": [dict(r) for r in ledger_tail],
    }

    # Canonical hash of the bundle (deterministic JSON)
    bundle_json   = json.dumps(bundle, separators=(",", ":"), sort_keys=True)
    bundle_sha256 = hashlib.sha256(bundle_json.encode()).hexdigest()
    bundle["bundle_sha256"] = bundle_sha256

    lid = ledger.append(
        action="EXPORT",
        payload={"alert_id": alert_id, "bundle_sha256": bundle_sha256},
        actor="system",
        db_path=_DB,
    )
    bundle["ledger_id"] = lid
    return bundle
