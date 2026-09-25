"""
chain/node.py — One agency's copy of the chain (its own SQLite file + key).
A node stores a block only after validating it itself, then endorses it.
audit() re-verifies the whole stored chain from genesis, trusting nothing on disk.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from app.chain import DATA_DIR, GENESIS_HASH
from app.chain.crypto import sign
from app.chain.validate import check_block, check_endorsements, registry_from

SCHEMA = """
CREATE TABLE IF NOT EXISTS blocks (
    height INTEGER PRIMARY KEY, ts TEXT NOT NULL, prev_block_hash TEXT NOT NULL,
    merkle_root TEXT NOT NULL, first_seq INTEGER NOT NULL, n_entries INTEGER NOT NULL,
    proposer TEXT NOT NULL, block_hash TEXT NOT NULL, proposer_sig TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS entries (
    seq INTEGER PRIMARY KEY, block_height INTEGER NOT NULL, ts TEXT NOT NULL,
    actor TEXT NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL,
    prev_hash TEXT NOT NULL, row_hash TEXT NOT NULL,
    signer_pub TEXT NOT NULL, signature TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS endorsements (
    height INTEGER NOT NULL, node TEXT NOT NULL, signature TEXT NOT NULL,
    PRIMARY KEY (height, node));
"""
_ENTRY_COLS = ["seq", "block_height", "ts", "actor", "action", "payload", "prev_hash", "row_hash", "signer_pub", "signature"]
_BLOCK_COLS = ["height", "ts", "prev_block_hash", "merkle_root", "first_seq", "n_entries",
               "proposer", "block_hash", "proposer_sig"]


class Node:
    def __init__(self, name: str):
        self.name = name
        self.path = DATA_DIR / name / "node.db"

    @contextmanager
    def _conn(self):
        """Open, yield, commit and always close (Windows keeps files locked otherwise)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(SCHEMA)
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ── Reads ─────────────────────────────────────────────────────────────
    def head(self) -> dict | None:
        with self._conn() as c:
            b = c.execute("SELECT height, block_hash FROM blocks ORDER BY height DESC LIMIT 1").fetchone()
            e = c.execute("SELECT seq, row_hash FROM entries ORDER BY seq DESC LIMIT 1").fetchone()
        if not b:
            return None
        return {"height": b["height"], "block_hash": b["block_hash"],
                "seq": e["seq"] if e else 0, "row_hash": e["row_hash"] if e else GENESIS_HASH}

    def blocks(self, limit: int = 1000, before: int | None = None) -> list[dict]:
        q, args = "SELECT * FROM blocks", []
        if before is not None:
            q, args = q + " WHERE height < ?", [before]
        with self._conn() as c:
            return [dict(r) for r in c.execute(q + " ORDER BY height DESC LIMIT ?", args + [limit])]

    def entries(self, height: int | None = None, limit: int = 100000) -> list[dict]:
        with self._conn() as c:
            if height is None:
                rows = c.execute("SELECT * FROM entries ORDER BY seq LIMIT ?", (limit,))
            else:
                rows = c.execute("SELECT * FROM entries WHERE block_height=? ORDER BY seq", (height,))
            return [dict(r) for r in rows]

    def endorsements(self, height: int) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM endorsements WHERE height=?", (height,))]

    def registry(self) -> dict:
        first = self.entries(limit=1)
        return registry_from(first[0]) if first else {}

    # ── Writes ────────────────────────────────────────────────────────────
    def check(self, block: dict, entries: list[dict], registry: dict | None = None) -> list[str]:
        """Validate a proposed block against *our own* tip. Returns errors ([] = valid)."""
        tip = self.head()
        if tip and block["height"] != tip["height"] + 1:
            return [f"expected block {tip['height'] + 1}, got {block['height']} (out of sync)"]
        reg = registry if tip is None else self.registry()
        return check_block(block, entries, tip["block_hash"] if tip else GENESIS_HASH,
                           tip["row_hash"] if tip else GENESIS_HASH, reg)

    def store(self, block: dict, entries: list[dict]) -> None:
        with self._conn() as c:
            c.execute(f"INSERT INTO blocks VALUES ({','.join('?' * len(_BLOCK_COLS))})",
                      [block[k] for k in _BLOCK_COLS])
            c.executemany(f"INSERT INTO entries VALUES ({','.join('?' * len(_ENTRY_COLS))})",
                          [[e[k] for k in _ENTRY_COLS] for e in entries])

    def endorse(self, block_hash: str) -> str:
        return sign(self.name, block_hash)

    def store_endorsements(self, height: int, sigs: dict[str, str]) -> None:
        with self._conn() as c:
            c.executemany("INSERT OR REPLACE INTO endorsements VALUES (?,?,?)",
                          [(height, n, s) for n, s in sigs.items()])

    def replace_with(self, source: "Node") -> None:
        """Re-sync: discard local state and copy a healthy peer's chain."""
        blocks, entries = source.blocks()[::-1], source.entries()
        ends = [en for b in blocks for en in source.endorsements(b["height"])]
        with self._conn() as c:
            for t in ("blocks", "entries", "endorsements"):
                c.execute(f"DELETE FROM {t}")
            c.executemany(f"INSERT INTO blocks VALUES ({','.join('?' * len(_BLOCK_COLS))})",
                          [[b[k] for k in _BLOCK_COLS] for b in blocks])
            c.executemany(f"INSERT INTO entries VALUES ({','.join('?' * len(_ENTRY_COLS))})",
                          [[e[k] for k in _ENTRY_COLS] for e in entries])
            c.executemany("INSERT INTO endorsements VALUES (?,?,?)",
                          [(en["height"], en["node"], en["signature"]) for en in ends])

    # ── Full audit ────────────────────────────────────────────────────────
    def audit(self) -> dict:
        """Re-verify every block, entry, signature and Merkle root from genesis."""
        blocks, entries = self.blocks()[::-1], self.entries()
        by_height: dict[int, list[dict]] = {}
        for e in entries:
            by_height.setdefault(e["block_height"], []).append(e)
        errors, bad_blocks, first_bad_entry = [], [], None
        reg = registry_from(entries[0]) if entries else {}
        prev_block, prev_row = GENESIS_HASH, GENESIS_HASH
        for b in blocks:
            errs = check_block(b, by_height.get(b["height"], []), prev_block, prev_row, reg)
            errs += check_endorsements(b, self.endorsements(b["height"]), reg)
            if errs:
                bad_blocks.append(b["height"])
                errors.extend(errs)
                if first_bad_entry is None:
                    first_bad_entry = next((int(s.split()[1].rstrip(":")) for s in errs
                                            if s.startswith("entry ")), None)
            prev_block = b["block_hash"]
            prev_row = by_height[b["height"]][-1]["row_hash"] if by_height.get(b["height"]) else prev_row
        tip = self.head()
        return {"node": self.name, "ok": not errors, "errors": errors[:8],
                "bad_blocks": bad_blocks, "first_broken_entry": first_bad_entry,
                "height": tip["height"] if tip else -1, "entries": len(entries),
                "head_hash": tip["block_hash"] if tip else None}
