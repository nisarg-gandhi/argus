"""
ingest.py — Source schema, wiping and CSV ingestion into argus.db.

argus.db holds *case data only*. The evidence ledger lives on the chain
nodes (app/chain/), so re-ingesting data can never erase audit history.
"""

from __future__ import annotations

import pathlib
import re
import sqlite3
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS fir (
    id TEXT PRIMARY KEY, station TEXT NOT NULL, date TEXT NOT NULL,
    section TEXT NOT NULL, narrative TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS person (
    id TEXT PRIMARY KEY, fir_id TEXT NOT NULL REFERENCES fir(id), name TEXT NOT NULL,
    alias TEXT, father_name TEXT, age TEXT,
    role TEXT NOT NULL CHECK(role IN ('VICTIM','WITNESS','ACCUSED','UNKNOWN')),
    address TEXT, phone TEXT, vehicle TEXT, account_no TEXT, imei TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS cdr (
    id TEXT PRIMARY KEY, caller TEXT NOT NULL, callee TEXT NOT NULL, ts TEXT NOT NULL,
    duration_s INTEGER NOT NULL, tower_loc TEXT);
CREATE TABLE IF NOT EXISTS bank_txn (
    id TEXT PRIMARY KEY, account_no TEXT NOT NULL, holder_name TEXT NOT NULL,
    linked_phone TEXT, txn_type TEXT NOT NULL CHECK(txn_type IN ('CREDIT','DEBIT','TRANSFER')),
    amount REAL NOT NULL, ts TEXT NOT NULL, counterpart TEXT);
CREATE TABLE IF NOT EXISTS vehicle_reg (
    id TEXT PRIMARY KEY, reg_no TEXT NOT NULL UNIQUE, owner_name TEXT NOT NULL,
    make TEXT, model TEXT, colour TEXT, chassis_no TEXT);
"""

SOURCE_TABLES = ["fir", "person", "cdr", "bank_txn", "vehicle_reg"]
DERIVED_TABLES = ["match_pairs", "golden_entities", "review_queue", "human_decisions",
                  "master_entity", "alerts", "feedback", "extraction", "pipeline_state"]
_COLUMNS = {
    "person": ["id", "fir_id", "name", "alias", "father_name", "age", "role", "address",
               "phone", "vehicle", "account_no", "imei", "notes"],
}


def wipe(conn: sqlite3.Connection) -> None:
    """Drop case data and everything derived from it (the ledger is untouched)."""
    for t in DERIVED_TABLES + list(reversed(SOURCE_TABLES)):
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.commit()


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _clean(table: str, row: dict[str, Any]) -> dict[str, Any]:
    """Standardise identifiers so strong-ID matching is exact."""
    row = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
    for k in ("phone", "linked_phone", "caller", "callee"):
        if row.get(k):
            digits = re.sub(r"\D", "", row[k])
            row[k] = digits[-10:] if len(digits) >= 10 else digits
    for k in ("vehicle", "reg_no"):
        if row.get(k):
            row[k] = re.sub(r"[\s-]", "", row[k]).upper()
    if table == "person":
        row = {c: (row.get(c) or None) for c in _COLUMNS["person"]}
    if table == "bank_txn" and isinstance(row.get("amount"), str):
        row["amount"] = float(row["amount"] or 0)
    if table == "cdr" and isinstance(row.get("duration_s"), str):
        row["duration_s"] = int(row["duration_s"] or 0)
    return row


def _insert(conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
    conn.executemany(sql, [tuple(r.get(c) for c in cols) for r in rows])


def ingest_data(db_path: pathlib.Path | str,
                table_data: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    """Wipe case data, recreate schema, clean + insert rows. Returns rows per table."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    summary: dict[str, int] = {}
    try:
        wipe(conn)
        create_schema(conn)
        for table in SOURCE_TABLES:
            rows = [_clean(table, r) for r in table_data.get(table, [])]
            _insert(conn, table, rows)
            summary[table] = len(rows)
        conn.commit()
    finally:
        conn.close()
    return summary
