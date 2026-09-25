"""
routes/ingest.py — POST /ingest (CSV/ZIP upload) and POST /ingest/demo.

Each source file is fingerprinted (SHA-256) and the fingerprints are sealed
on the evidence chain *before* any processing — the "Hashing" step of the
deck's flow — so later tampering with source data is provable.
"""

from __future__ import annotations

import csv
import hashlib
import io
import pathlib
import zipfile

from fastapi import APIRouter, File, HTTPException, UploadFile

from app import ledger
from app.ingest import ingest_data

router = APIRouter(tags=["ingest"])
_DB = pathlib.Path(__file__).resolve().parent.parent.parent / "argus.db"
_DEMO = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "demo_case"
_LABELS = {"fir": "FIR / police reports", "person": "Persons named in FIRs", "cdr": "Call detail records",
           "bank_txn": "Bank transactions", "vehicle_reg": "RTO vehicle registry"}


def _table_for(filename: str) -> str:
    name = filename.lower().rsplit("/", 1)[-1].replace(".csv", "")
    for key, table in (("fir", "fir"), ("person", "person"), ("cdr", "cdr"),
                       ("bank", "bank_txn"), ("vehicle", "vehicle_reg")):
        if key in name:
            return table
    return ""


def _process_files(files: list[tuple[str, bytes]], actor: str) -> dict:
    table_data, manifest = {}, []
    for fname, content in files:
        table = _table_for(fname)
        if not table:
            continue
        rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
        table_data[table] = rows
        manifest.append({"file": fname.rsplit("/", 1)[-1], "table": table, "source": _LABELS[table],
                         "rows": len(rows), "bytes": len(content),
                         "sha256": hashlib.sha256(content).hexdigest()})
    if not table_data:
        raise HTTPException(422, "No recognised CSV files (expected fir/person/cdr/bank/vehicle)")
    summary = ingest_data(_DB, table_data)
    block = ledger.append_many([("INGEST_FILE", m, actor) for m in manifest])
    return {"status": "success", "summary": summary, "files": manifest, "block": block}


@router.post("/ingest")
async def ingest_files(files: list[UploadFile] = File(...)):
    collected: list[tuple[str, bytes]] = []
    for f in files:
        content = await f.read()
        if f.filename.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                collected += [(i.filename, z.read(i.filename)) for i in z.infolist()
                              if i.filename.lower().endswith(".csv")]
        elif f.filename.lower().endswith(".csv"):
            collected.append((f.filename, content))
    return _process_files(collected, "analyst")


@router.post("/ingest/demo")
def ingest_demo():
    """Load the bundled Lucknow demo case (same path as a real upload)."""
    files = [(p.name, p.read_bytes()) for p in sorted(_DEMO.glob("*.csv"))]
    return _process_files(files, "analyst")
