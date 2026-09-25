"""
routes/audit.py — Evidence Chain API.

  GET  /chain/status           full audit of all 3 nodes + consensus
  GET  /chain/blocks           block headers (newest first) with endorsements
  GET  /chain/block/{height}   one block: header, signed entries, Merkle tree
  POST /chain/heal/{node}      re-sync a tampered / out-of-sync node from peers
  GET  /chain/proof/{seq}      Merkle inclusion proof for one entry
  GET  /ledger, /ledger/verify legacy views (kept for compatibility)
  POST /demo/tamper            same raw-file edit as `python -m app.chain.tamper`
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import ledger
from app.chain import NODE_LABELS, NODES
from app.chain.crypto import fingerprint
from app.chain.merkle import levels
from app.chain.network import heal, healthy_node, inclusion_proof, status
from app.chain.node import Node

router = APIRouter(tags=["evidence chain"])


@router.get("/chain/status")
def chain_status():
    return status()


@router.get("/chain/blocks")
def chain_blocks(limit: int = 40, node: str | None = None):
    src = Node(node) if node in NODES else healthy_node()
    blocks = src.blocks(limit)
    for b in blocks:
        b["endorsed_by"] = sorted(e["node"] for e in src.endorsements(b["height"]))
        b["actions"] = sorted({e["action"] for e in src.entries(b["height"])})
    return {"node": src.name, "blocks": blocks}


@router.get("/chain/block/{height}")
def chain_block(height: int, node: str | None = None):
    src = Node(node) if node in NODES else healthy_node()
    block = next((b for b in src.blocks() if b["height"] == height), None)
    if not block:
        raise HTTPException(404, f"Block {height} not found")
    entries = src.entries(height)
    for e in entries:
        e["data"] = json.loads(e["payload"]).get("data", {})
        e["signer_fp"] = fingerprint(e["signer_pub"])
    return {"node": src.name, "block": block, "entries": entries,
            "endorsements": [{**e, "label": NODE_LABELS[e["node"]]} for e in src.endorsements(height)],
            "merkle_levels": levels([e["row_hash"] for e in entries])}


@router.post("/chain/heal/{node}")
def chain_heal(node: str):
    if node not in NODES:
        raise HTTPException(404, f"Unknown node {node}")
    return heal(node)


@router.get("/chain/proof/{seq}")
def chain_proof(seq: int):
    try:
        return inclusion_proof(seq)
    except KeyError:
        raise HTTPException(404, f"Entry {seq} not found")


@router.get("/ledger")
def get_ledger(limit: int = 50):
    return {"entries": ledger.rows(limit=limit)}


@router.get("/ledger/verify")
def verify_ledger():
    broken = ledger.verify_chain()
    return {"intact": broken is None, "first_broken_index": broken,
            "message": "Chain intact" if broken is None else f"Chain broken at entry {broken}"}


class TamperBody(BaseModel):
    row_id: int | None = None
    node: str = "forensic_lab"
    rehash: bool = False


@router.post("/demo/tamper")
def demo_tamper(body: TamperBody):
    """FOR DEMO ONLY — edits one node's SQLite file directly, like an insider would."""
    if body.node not in NODES:
        raise HTTPException(404, f"Unknown node {body.node}")
    return ledger.tamper(body.row_id, node=body.node, rehash=body.rehash)
