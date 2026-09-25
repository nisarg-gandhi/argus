"""
ledger.py — Append-only SHA-256 chained audit ledger backed by SQLite.

Schema (table: ledger):
  id        INTEGER PRIMARY KEY AUTOINCREMENT
  ts        TEXT NOT NULL   -- ISO-8601 UTC
  actor     TEXT NOT NULL   -- user/system identifier
  action    TEXT NOT NULL   -- PROCESS | MERGE | REJECT | REVIEW_SUBMIT | FEEDBACK | TAMPER
  payload   TEXT NOT NULL   -- JSON blob (event-specific)
  prev_hash TEXT NOT NULL   -- row_hash of the previous row (GENESIS for row 1)
  row_hash  TEXT NOT NULL   -- sha256(prev_hash + payload)

/ledger/verify walks the chain and returns first broken index or None.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sqlite3
from datetime import datetime, timezone

_HERE   = pathlib.Path(__file__).resolve().parent
DB_PATH = _HERE.parent / "argus.db"

_GENESIS = "0" * 64   # sentinel prev_hash for the first row


def append(
    action: str,
    payload: dict,
    actor: str = "system",
    db_path: str | pathlib.Path = DB_PATH,
) -> int:
    """Append a new row to the ledger. Returns the new row id."""
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    ts = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(str(db_path))
    try:
        # Fetch previous row_hash (or GENESIS if table is empty)
        row = conn.execute(
            "SELECT row_hash FROM ledger ORDER BY id DESC LIMIT 1"
        ).fetchone()
        prev_hash = row[0] if row else _GENESIS
        row_hash  = _hash(prev_hash, payload_json)

        cur = conn.execute(
            "INSERT INTO ledger(ts, actor, action, payload, prev_hash, row_hash) "
            "VALUES (?,?,?,?,?,?)",
            (ts, actor, action, payload_json, prev_hash, row_hash),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def verify_chain(db_path: str | pathlib.Path = DB_PATH) -> int | None:
    """Walk every ledger row in order; return 1-based index of first broken
    link, or None if the chain is intact."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT id, payload, prev_hash, row_hash FROM ledger ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    expected_prev = _GENESIS
    for idx, (row_id, payload, prev_hash, row_hash) in enumerate(rows, start=1):
        if prev_hash != expected_prev:
            return idx
        if _hash(prev_hash, payload) != row_hash:
            return idx
        expected_prev = row_hash

    return None   # chain intact


def tamper(row_id: int, db_path: str | pathlib.Path = DB_PATH) -> dict:
    """FOR DEMO ONLY — corrupt one row to prove verify catches it."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE ledger SET payload = json_set(payload, '$.tampered', true) WHERE id=?",
            (row_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return {"tampered_row": row_id}


def rows(db_path: str | pathlib.Path = DB_PATH, limit: int = 100) -> list[dict]:
    """Return the most-recent ledger rows as dicts."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return [
            dict(r) for r in conn.execute(
                "SELECT * FROM ledger ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        ]
    finally:
        conn.close()


def _hash(prev_hash: str, payload_json: str) -> str:
    return hashlib.sha256((prev_hash + payload_json).encode()).hexdigest()
