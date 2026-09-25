"""
chain/validate.py — The rules every node applies, both when a new block
arrives and when auditing its whole stored chain.

Entry  : row_hash  = sha256(prev_hash + payload)          (CLAUDE.md formula)
         payload   = canonical JSON {seq, ts, actor, action, data}
         signature = Ed25519(actor key, row_hash)
Block  : header    = {height, ts, prev_block_hash, merkle_root, first_seq, n_entries, proposer}
         block_hash = sha256(canonical(header));  proposer_sig = Ed25519(proposer node, block_hash)
"""

from __future__ import annotations

import json

from app.chain import NODES
from app.chain.crypto import canonical, sha256, verify
from app.chain.merkle import root

HEADER_FIELDS = ["height", "ts", "prev_block_hash", "merkle_root", "first_seq", "n_entries", "proposer"]


def header_hash(block: dict) -> str:
    return sha256(canonical({k: block[k] for k in HEADER_FIELDS}))


def registry_from(genesis_entry: dict) -> dict:
    return json.loads(genesis_entry["payload"])["data"]["registry"]


def check_entry(e: dict, prev_hash: str, seq: int, registry: dict) -> str | None:
    """Return an error string, or None if the entry is valid."""
    if e["seq"] != seq:
        return f"entry {e['seq']}: expected sequence {seq}"
    if e["prev_hash"] != prev_hash:
        return f"entry {seq}: prev_hash does not link to entry {seq - 1}"
    if sha256(e["prev_hash"] + e["payload"]) != e["row_hash"]:
        return f"entry {seq}: content was modified (row_hash mismatch)"
    try:
        env = json.loads(e["payload"])
    except ValueError:
        return f"entry {seq}: payload is not valid JSON"
    if (env.get("seq"), env.get("actor"), env.get("action"), env.get("ts")) != \
            (e["seq"], e["actor"], e["action"], e["ts"]):
        return f"entry {seq}: indexed columns disagree with signed payload"
    expected_pub = registry.get("actors", {}).get(e["actor"])
    if expected_pub != e["signer_pub"]:
        return f"entry {seq}: signer is not the registered key for '{e['actor']}'"
    if not verify(e["signer_pub"], e["row_hash"], e["signature"]):
        return f"entry {seq}: signature by '{e['actor']}' is INVALID"
    return None


def check_block(block: dict, entries: list[dict], prev_block_hash: str,
                prev_row_hash: str, registry: dict) -> list[str]:
    """Validate a block and its entries against the chain tip they extend."""
    errs: list[str] = []
    h = block["height"]
    if block["prev_block_hash"] != prev_block_hash:
        errs.append(f"block {h}: does not link to block {h - 1}")
    if block["proposer"] != NODES[h % len(NODES)]:
        errs.append(f"block {h}: proposer {block['proposer']} is out of turn")
    if len(entries) != block["n_entries"]:
        errs.append(f"block {h}: expected {block['n_entries']} entries, found {len(entries)}")
    prev = prev_row_hash
    for i, e in enumerate(entries):
        err = check_entry(e, prev, block["first_seq"] + i, registry)
        if err:
            errs.append(err)
            break
        prev = e["row_hash"]
    if root([e["row_hash"] for e in entries]) != block["merkle_root"]:
        errs.append(f"block {h}: Merkle root does not match its entries")
    if header_hash(block) != block["block_hash"]:
        errs.append(f"block {h}: header was modified (block_hash mismatch)")
    node_pub = registry.get("nodes", {}).get(block["proposer"], "")
    if not verify(node_pub, block["block_hash"], block["proposer_sig"]):
        errs.append(f"block {h}: proposer signature INVALID")
    return errs


def check_endorsements(block: dict, endorsements: list[dict], registry: dict) -> list[str]:
    errs = []
    for en in endorsements:
        pub = registry.get("nodes", {}).get(en["node"], "")
        if not verify(pub, block["block_hash"], en["signature"]):
            errs.append(f"block {block['height']}: endorsement by {en['node']} INVALID")
    return errs
