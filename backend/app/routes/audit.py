"""
routes/audit.py — GET /ledger, GET /ledger/verify, POST /demo/tamper
Ledger inspection and demo-tamper endpoint.
"""

from __future__ import annotations

import pathlib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import ledger

router = APIRouter(tags=["audit"])

_DB = pathlib.Path(__file__).resolve().parent.parent.parent / "argus.db"


@router.get("/ledger")
def get_ledger(limit: int = 50):
    """Return the most-recent *limit* ledger rows (newest first)."""
    return {"entries": ledger.rows(db_path=_DB, limit=limit)}


@router.get("/ledger/verify")
def verify_ledger():
    """Walk the hash chain. Returns first broken index or null if intact.

    Use this in the demo to prove tamper-evidence.
    """
    broken = ledger.verify_chain(db_path=_DB)
    return {
        "intact": broken is None,
        "first_broken_index": broken,
        "message": "Chain intact" if broken is None
                   else f"Chain broken at row index {broken}",
    }


class TamperBody(BaseModel):
    row_id: int = 1


@router.post("/demo/tamper")
def demo_tamper(body: TamperBody):
    """FOR DEMO ONLY — corrupt one ledger row to show verify catches it.

    After calling this, GET /ledger/verify will return first_broken_index != null.
    Recover by running `python -m app.seed --reset` which rebuilds argus.db.
    """
    rows = ledger.rows(db_path=_DB, limit=1000)
    ids  = {r["id"] for r in rows}
    if body.row_id not in ids:
        raise HTTPException(
            status_code=404,
            detail=f"Ledger row {body.row_id} not found. "
                   f"Valid IDs: {sorted(ids)[:10]} …"
        )
    result = ledger.tamper(body.row_id, db_path=_DB)
    return {
        **result,
        "message": f"Row {body.row_id} corrupted. Call GET /ledger/verify to confirm.",
        "recover": "python -m app.seed --reset",
    }
