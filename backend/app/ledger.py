"""
ledger.py — Application-facing facade over the Argus Evidence Chain.

Every audit event (ingest, resolution decisions, feedback, exports) becomes a
signed entry in a block that all three agency nodes validate and endorse.
row_hash = sha256(prev_hash + payload_json) as CLAUDE.md specifies; the chain
adds signatures, Merkle roots, blocks and multi-node consensus on top.
The legacy `db_path` arguments are accepted and ignored (the chain lives in
backend/chain_data, not argus.db, so re-ingesting case data never erases it).
"""

from __future__ import annotations

import json

from app.chain import network
from app.chain import tamper as _tamper


def append(action: str, payload: dict, actor: str = "system", db_path=None) -> int:
    """Commit one entry in its own block. Returns the entry sequence number."""
    return network.commit([(action, payload, actor)])["seqs"][0]


def append_many(items: list[tuple[str, dict, str]]) -> dict:
    """Commit several (action, payload, actor) entries as ONE block."""
    return network.commit(items)


def verify_chain(db_path=None) -> int | None:
    """First broken entry on any node, or None if every node is intact."""
    for n in network.status()["nodes"]:
        if not n["ok"]:
            return n["first_broken_entry"] or 1
    return None


def rows(db_path=None, limit: int = 100) -> list[dict]:
    """Most recent entries (newest first) from a node that holds consensus."""
    entries = network.healthy_node().entries()[-limit:][::-1]
    out = []
    for e in entries:
        env = json.loads(e["payload"])
        out.append({"id": e["seq"], "seq": e["seq"], "block": e["block_height"], "ts": e["ts"],
                    "actor": e["actor"], "action": e["action"], "data": env.get("data", {}),
                    "prev_hash": e["prev_hash"], "row_hash": e["row_hash"],
                    "signature": e["signature"], "signer_pub": e["signer_pub"]})
    return out


def tamper(row_id: int, db_path=None, node: str = "forensic_lab", rehash: bool = False) -> dict:
    """FOR DEMO ONLY — the same raw file edit the `app.chain.tamper` CLI performs."""
    return {"tampered_row": row_id, "node": node, "log": _tamper.run(node, row_id, rehash)}
