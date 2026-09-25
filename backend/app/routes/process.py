"""
routes/process.py — POST /process
Runs the full pipeline: extract -> resolve -> graph build -> analyse.
Single endpoint for the "System Processes the Data" demo beat.
"""

from __future__ import annotations

import pathlib
import sqlite3

from fastapi import APIRouter
from pydantic import BaseModel

from app import extract, ledger
from app.resolve import resolve_all
from app.analyse import run_alert_rules

router = APIRouter(tags=["pipeline"])

_DB = pathlib.Path(__file__).resolve().parent.parent.parent / "argus.db"


class ProcessResponse(BaseModel):
    extracted_firs: int
    resolution: dict
    alerts_generated: int
    ledger_id: int


@router.post("/process", response_model=ProcessResponse)
def run_pipeline():
    """Run the full extract -> resolve -> analyse pipeline over all FIRs.

    Safe to call multiple times; resolve_all() clears previous results
    before re-running.
    """
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row

    # 1. Extract entities from all FIR narratives
    firs = conn.execute("SELECT id, narrative FROM fir").fetchall()
    conn.close()

    extracted: list[dict] = []
    for fir in firs:
        result = extract.extract_entities(fir["narrative"])
        result["fir_id"] = fir["id"]
        extracted.append(result)

    # 2. Resolve persons across FIRs
    resolution = resolve_all(_DB)

    # 3. Analyse: run alert rules (graph built internally)
    alerts = run_alert_rules(_DB)

    # 4. Ledger entry
    lid = ledger.append(
        action="PROCESS",
        payload={
            "firs_processed": len(firs),
            "resolution": resolution,
            "alerts": len(alerts),
        },
        actor="system",
        db_path=_DB,
    )

    return ProcessResponse(
        extracted_firs=len(firs),
        resolution=resolution,
        alerts_generated=len(alerts),
        ledger_id=lid,
    )
