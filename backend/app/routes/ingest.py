"""
routes/ingest.py — POST /ingest
Accepts CSV or ZIP uploads, parses them, and seeds the database.
"""

from __future__ import annotations

import io
import csv
import zipfile
import pathlib

from fastapi import APIRouter, UploadFile, File

from app.ingest import ingest_data

router = APIRouter(tags=["ingest"])

_DB = pathlib.Path(__file__).resolve().parent.parent.parent / "argus.db"


@router.post("/ingest")
async def ingest_files(files: list[UploadFile] = File(...)):
    """Accept multiple CSVs or a ZIP file and parse into the database."""
    table_data = {}
    
    for file in files:
        content = await file.read()
        filename = file.filename.lower()
        
        if filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                for zinfo in z.infolist():
                    if zinfo.filename.endswith(".csv"):
                        csv_content = z.read(zinfo.filename).decode("utf-8")
                        table_name = _get_table_name(zinfo.filename)
                        if table_name:
                            reader = csv.DictReader(io.StringIO(csv_content))
                            table_data[table_name] = list(reader)
        elif filename.endswith(".csv"):
            csv_content = content.decode("utf-8")
            table_name = _get_table_name(filename)
            if table_name:
                reader = csv.DictReader(io.StringIO(csv_content))
                table_data[table_name] = list(reader)
                
    # Wipes existing DB and inserts the new rows
    summary = ingest_data(_DB, table_data)
    
    return {
        "status": "success",
        "message": "Data ingested successfully",
        "summary": summary
    }


def _get_table_name(filename: str) -> str:
    """Map filename to database table name."""
    name = filename.lower().replace(".csv", "").split("/")[-1]
    if "fir" in name: return "fir"
    if "person" in name: return "person"
    if "cdr" in name: return "cdr"
    if "bank" in name: return "bank_txn"
    if "vehicle" in name: return "vehicle_reg"
    return ""
