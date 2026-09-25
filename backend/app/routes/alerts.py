"""
routes/alerts.py — Alerts, analyst feedback and BSA s.63(4) evidence export.

  GET  /alerts                     alerts with evidence + latest analyst verdict
  POST /alert/{id}/feedback        TP/FP/TN/FN -> feedback table + signed chain entry
  GET  /feedback/stats             precision per rule (no model training, per CLAUDE.md)
  GET  /export/{id}                evidence bundle, SHA-256 sealed and anchored on-chain
                                   with a Merkle proof (verify: python -m app.chain.verify --evidence)
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import ledger
from app.chain.crypto import canonical, sha256
from app.chain.network import inclusion_proof

router = APIRouter(tags=["alerts"])
_DB = pathlib.Path(__file__).resolve().parent.parent.parent / "argus.db"
_FEEDBACK = """CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id INTEGER NOT NULL, rule TEXT,
    verdict TEXT NOT NULL CHECK(verdict IN ('tp','fp','tn','fn')),
    actor TEXT NOT NULL, notes TEXT, ts TEXT NOT NULL)"""


class FeedbackBody(BaseModel):
    verdict: str
    actor: str = "analyst"
    notes: str = ""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    conn.execute(_FEEDBACK)
    return conn


def _alert(row) -> dict:
    return {**{k: row[k] for k in row.keys() if not k.endswith("_json")},
            "entities": json.loads(row["entities_json"]), "source_ids": json.loads(row["source_ids_json"]),
            "evidence": json.loads(row["evidence_json"])}


@router.get("/alerts")
def list_alerts():
    conn = _conn()
    try:
        try:
            rows = conn.execute("SELECT * FROM alerts ORDER BY confidence DESC").fetchall()
        except sqlite3.OperationalError:
            return {"alerts": [], "count": 0}
        verdicts = {r["alert_id"]: r["verdict"] for r in conn.execute("SELECT alert_id, verdict FROM feedback ORDER BY id")}
        alerts = [{**_alert(r), "verdict": verdicts.get(r["id"])} for r in rows]
        return {"alerts": alerts, "count": len(alerts)}
    finally:
        conn.close()


@router.post("/alert/{alert_id}/feedback")
def submit_feedback(alert_id: int, body: FeedbackBody):
    if body.verdict not in ("tp", "fp", "tn", "fn"):
        raise HTTPException(422, "verdict must be tp/fp/tn/fn")
    conn = _conn()
    try:
        alert = conn.execute("SELECT id, rule, title FROM alerts WHERE id=?", (alert_id,)).fetchone()
        if not alert:
            raise HTTPException(404, f"Alert {alert_id} not found")
        cur = conn.execute("INSERT INTO feedback(alert_id, rule, verdict, actor, notes, ts) VALUES (?,?,?,?,?,?)",
                           (alert_id, alert["rule"], body.verdict, body.actor, body.notes,
                            datetime.now(timezone.utc).isoformat()))
        conn.commit()
        fid = cur.lastrowid
    finally:
        conn.close()
    block = ledger.append_many([("FEEDBACK", {"alert_id": alert_id, "rule": alert["rule"], "title": alert["title"],
                                              "verdict": body.verdict, "feedback_id": fid}, body.actor)])
    return {"feedback_id": fid, "verdict": body.verdict, "ledger_id": block["seqs"][0], "block": block["height"]}


@router.get("/feedback/stats")
def feedback_stats():
    conn = _conn()
    try:
        rows = conn.execute("SELECT rule, verdict, COUNT(*) n FROM feedback GROUP BY rule, verdict").fetchall()
    finally:
        conn.close()
    stats: dict[str, dict] = {}
    for r in rows:
        stats.setdefault(r["rule"], {"tp": 0, "fp": 0, "tn": 0, "fn": 0})[r["verdict"]] = r["n"]
    for s in stats.values():
        s["precision"] = round(s["tp"] / (s["tp"] + s["fp"]), 3) if s["tp"] + s["fp"] else None
    return {"by_rule": stats}


@router.get("/export/{alert_id}")
def export_evidence(alert_id: int):
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"Alert {alert_id} not found")
        alert = _alert(row)
        records = []
        for sid in alert["source_ids"]:
            for tbl, col in (("fir", "id"), ("cdr", "id"), ("bank_txn", "id"), ("bank_txn", "account_no")):
                records += [{"table": tbl, "record": dict(r)} for r in
                            conn.execute(f"SELECT * FROM {tbl} WHERE {col}=? LIMIT 5", (sid,))]
    finally:
        conn.close()
    bundle = {"bsa_section": "63(4)", "exported_at": datetime.now(timezone.utc).isoformat(),
              "exported_by": "analyst", "alert": alert, "source_records": records,
              "certificate": "Certified that the electronic records herein were produced by the Argus system "
                             "in the ordinary course of its operation, and are anchored on the multi-agency "
                             "evidence chain referenced below."}
    bundle["bundle_sha256"] = sha256(canonical(bundle))
    res = ledger.append_many([("EXPORT", {"alert_id": alert_id, "bundle_sha256": bundle["bundle_sha256"],
                                          "records": len(records)}, "analyst")])
    p = inclusion_proof(res["seqs"][0])
    e, b = p["entry"], p["block"]
    bundle["anchor"] = {"seq": e["seq"], "block_height": b["height"], "block_hash": b["block_hash"],
                        "merkle_root": b["merkle_root"], "row_hash": e["row_hash"], "prev_hash": e["prev_hash"],
                        "payload": e["payload"], "signature": e["signature"], "signer_pub": e["signer_pub"],
                        "merkle_proof": p["merkle_proof"], "endorsed_by": res["endorsed_by"]}
    return bundle
