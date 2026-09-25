"""
chain/network.py — Propose -> validate on every node -> endorse -> commit.
commit() builds on the majority tip and stores a block only if a quorum (2 of 3)
validates it; status() audits every node from genesis; heal() re-syncs a bad node.
"""

from __future__ import annotations

import threading
from collections import Counter
from datetime import datetime, timezone

from app.chain import ACTORS, GENESIS_HASH, NODE_LABELS, NODES
from app.chain.crypto import canonical, fingerprint, public_hex, sha256, sign
from app.chain.merkle import proof as merkle_proof, root
from app.chain.node import Node
from app.chain.validate import header_hash

QUORUM = 2
_LOCK = threading.RLock()


def nodes() -> list[Node]:
    return [Node(n) for n in NODES]


def _build(height: int, prev_block: str, prev_row: str, first_seq: int,
           items: list[tuple[str, dict, str]]) -> tuple[dict, list[dict]]:
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    entries, prev = [], prev_row
    for i, (action, data, actor) in enumerate(items):
        seq = first_seq + i
        payload = canonical({"seq": seq, "ts": ts, "actor": actor, "action": action, "data": data})
        row_hash = sha256(prev + payload)
        entries.append({"seq": seq, "block_height": height, "ts": ts, "actor": actor,
                        "action": action, "payload": payload, "prev_hash": prev,
                        "row_hash": row_hash, "signer_pub": public_hex(actor),
                        "signature": sign(actor, row_hash)})
        prev = row_hash
    block = {"height": height, "ts": ts, "prev_block_hash": prev_block,
             "merkle_root": root([e["row_hash"] for e in entries]), "first_seq": first_seq,
             "n_entries": len(entries), "proposer": NODES[height % len(NODES)]}
    block["block_hash"] = header_hash(block)
    block["proposer_sig"] = sign(block["proposer"], block["block_hash"])
    return block, entries


def ensure_genesis() -> None:
    with _LOCK:
        ns = nodes()
        if all(n.head() for n in ns):
            return
        if any(n.head() for n in ns):                    # a node was wiped: re-sync it
            src = next(n for n in ns if n.head())
            for n in ns:
                if not n.head():
                    n.replace_with(src)
            return
        registry = {"nodes": {n: public_hex(n) for n in NODES},
                    "actors": {a: public_hex(a) for a in ACTORS}}
        block, entries = _build(0, GENESIS_HASH, GENESIS_HASH, 1, [(
            "GENESIS", {"network": NODE_LABELS, "registry": registry,
                        "legal_basis": "BSA 2023 s.63(4) - certified electronic records"}, "system")])
        _commit_block(ns, block, entries, registry)


def _commit_block(ns: list[Node], block: dict, entries: list[dict], registry=None) -> dict:
    verdicts = {n.name: n.check(block, entries, registry) for n in ns}
    ok = [n for n in ns if not verdicts[n.name]]
    if len(ok) < QUORUM:
        raise RuntimeError(f"Quorum not reached for block {block['height']}: "
                           + "; ".join(f"{k}: {v[0]}" for k, v in verdicts.items() if v))
    sigs = {}
    for n in ok:
        n.store(block, entries)
        sigs[n.name] = n.endorse(block["block_hash"])
    for n in ok:
        n.store_endorsements(block["height"], sigs)
    return {"height": block["height"], "block_hash": block["block_hash"],
            "merkle_root": block["merkle_root"], "proposer": block["proposer"],
            "seqs": [e["seq"] for e in entries], "endorsed_by": sorted(sigs),
            "rejected_by": {k: v[:2] for k, v in verdicts.items() if v}}


def _majority_tip(ns: list[Node]) -> tuple[Node, dict]:
    heads = {n.name: n.head() for n in ns}
    votes = Counter(h["block_hash"] for h in heads.values() if h)
    best, count = votes.most_common(1)[0]
    if count < QUORUM:
        raise RuntimeError("No majority tip: nodes disagree, heal the network first")
    node = next(n for n in ns if heads[n.name] and heads[n.name]["block_hash"] == best)
    return node, heads[node.name]


def commit(items: list[tuple[str, dict, str]]) -> dict:
    """Append one block containing *items* = [(action, data, actor), ...]."""
    ensure_genesis()
    with _LOCK:
        ns = nodes()
        _, tip = _majority_tip(ns)
        block, entries = _build(tip["height"] + 1, tip["block_hash"], tip["row_hash"], tip["seq"] + 1, items)
        return _commit_block(ns, block, entries)


def status() -> dict:
    ensure_genesis()
    with _LOCK:
        reports = [n.audit() for n in nodes()]
    votes = Counter(r["head_hash"] for r in reports if r["ok"])
    head, count = votes.most_common(1)[0] if votes else (None, 0)
    for r in reports:
        r["label"] = NODE_LABELS[r["node"]]
        r["key_fingerprint"] = fingerprint(public_hex(r["node"]))
        r["state"] = ("tampered" if not r["ok"] else
                      "in_consensus" if r["head_hash"] == head else "out_of_sync")
    return {"nodes": reports, "consensus": {"head_hash": head, "votes": count,
                                            "total": len(reports), "quorum": count >= QUORUM},
            "height": max((r["height"] for r in reports if r["head_hash"] == head), default=-1)}


def healthy_node() -> Node:
    name = next((r["node"] for r in status()["nodes"] if r["state"] == "in_consensus"), None)
    if not name:
        raise RuntimeError("No healthy node with consensus")
    return Node(name)


def heal(name: str) -> dict:
    """Replace a node's chain with the consensus copy, then log the repair on-chain."""
    with _LOCK:
        before = next(r for r in status()["nodes"] if r["node"] == name)
        src = healthy_node()
        Node(name).replace_with(src)
        res = commit([("NODE_RESYNC", {"node": name, "copied_from": src.name,
                                       "state_before": before["state"],
                                       "errors_found": before["errors"][:3]}, "system")])
    return {"node": name, "copied_from": src.name, "state_before": before["state"], "logged_in_block": res["height"]}


def inclusion_proof(seq: int) -> dict:
    """Merkle proof that entry *seq* is in its block (verifiable offline)."""
    src = healthy_node()
    e = next((x for x in src.entries() if x["seq"] == seq), None)
    if not e:
        raise KeyError(seq)
    block_entries = src.entries(e["block_height"])
    idx = [x["seq"] for x in block_entries].index(seq)
    block = next(b for b in src.blocks() if b["height"] == e["block_height"])
    return {"entry": e, "block": block, "leaf_index": idx,
            "merkle_proof": merkle_proof([x["row_hash"] for x in block_entries], idx)}
