"""
ingest.py — Handle database schema, wiping, and data ingestion from CSVs.
"""

from __future__ import annotations

import sqlite3
import pathlib
import csv
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS fir (
    id          TEXT PRIMARY KEY,
    station     TEXT NOT NULL,
    date        TEXT NOT NULL,
    section     TEXT NOT NULL,
    narrative   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS person (
    id          TEXT PRIMARY KEY,
    fir_id      TEXT NOT NULL REFERENCES fir(id),
    name        TEXT NOT NULL,
    role        TEXT NOT NULL CHECK(role IN ('VICTIM','WITNESS','ACCUSED','UNKNOWN')),
    address     TEXT,
    phone       TEXT,
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS cdr (
    id          TEXT PRIMARY KEY,
    caller      TEXT NOT NULL,
    callee      TEXT NOT NULL,
    ts          TEXT NOT NULL,
    duration_s  INTEGER NOT NULL,
    tower_loc   TEXT
);

CREATE TABLE IF NOT EXISTS bank_txn (
    id          TEXT PRIMARY KEY,
    account_no  TEXT NOT NULL,
    holder_name TEXT NOT NULL,
    linked_phone TEXT,
    txn_type    TEXT NOT NULL CHECK(txn_type IN ('CREDIT','DEBIT','TRANSFER')),
    amount      REAL NOT NULL,
    ts          TEXT NOT NULL,
    counterpart TEXT
);

CREATE TABLE IF NOT EXISTS vehicle_reg (
    id          TEXT PRIMARY KEY,
    reg_no      TEXT NOT NULL UNIQUE,
    owner_name  TEXT NOT NULL,
    make        TEXT,
    model       TEXT,
    colour      TEXT,
    chassis_no  TEXT
);

CREATE TABLE IF NOT EXISTS ledger (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    payload     TEXT NOT NULL,
    prev_hash   TEXT NOT NULL,
    row_hash    TEXT NOT NULL
);
"""

def wipe(conn: sqlite3.Connection) -> None:
    """Drop all seed tables."""
    tables = ["ledger", "vehicle_reg", "bank_txn", "cdr", "person", "fir"]
    for t in tables:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.commit()


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _insert(conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    placeholders = ",".join("?" * len(cols))
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
    conn.executemany(sql, [tuple(r.get(c) for c in cols) for r in rows])


def ingest_data(db_path: pathlib.Path | str, table_data: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    """
    Takes a dictionary mapping table names to lists of dictionaries (rows).
    Wipes the database, creates schema, casts types as necessary, and inserts rows.
    Returns a summary of rows inserted per table.
    """
    # Type casting for specific fields
    if "bank_txn" in table_data:
        for row in table_data["bank_txn"]:
            if "amount" in row and isinstance(row["amount"], str):
                try:
                    row["amount"] = float(row["amount"])
                except ValueError:
                    pass

    if "cdr" in table_data:
        for row in table_data["cdr"]:
            if "duration_s" in row and isinstance(row["duration_s"], str):
                try:
                    row["duration_s"] = int(row["duration_s"])
                except ValueError:
                    pass

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    summary = {}
    try:
        wipe(conn)
        create_schema(conn)

        for table in ["fir", "person", "cdr", "bank_txn", "vehicle_reg"]:
            if table in table_data:
                rows = table_data[table]
                _insert(conn, table, rows)
                summary[table] = len(rows)
            else:
                summary[table] = 0

        conn.commit()
    finally:
        conn.close()

    return summary
