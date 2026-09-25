"""
chain/merkle.py — Binary Merkle tree over entry hashes (Bitcoin-style:
an odd node is paired with itself). Proofs let anyone check that one entry
is inside a block using only the block header.
"""

from __future__ import annotations

from app.chain.crypto import sha256


def _parent(a: str, b: str) -> str:
    return sha256(a + b)


def levels(leaves: list[str]) -> list[list[str]]:
    """All tree levels, leaves first, root last."""
    if not leaves:
        return [[sha256("")]]
    out = [list(leaves)]
    while len(out[-1]) > 1:
        cur = out[-1]
        nxt = [_parent(cur[i], cur[i + 1] if i + 1 < len(cur) else cur[i])
               for i in range(0, len(cur), 2)]
        out.append(nxt)
    return out


def root(leaves: list[str]) -> str:
    return levels(leaves)[-1][0]


def proof(leaves: list[str], index: int) -> list[dict]:
    """Sibling path from leaf *index* to the root."""
    path = []
    for level in levels(leaves)[:-1]:
        sib = index ^ 1
        sibling = level[sib] if sib < len(level) else level[index]
        path.append({"hash": sibling, "side": "left" if sib < index else "right"})
        index //= 2
    return path


def verify_proof(leaf: str, path: list[dict], expected_root: str) -> bool:
    h = leaf
    for step in path:
        h = _parent(step["hash"], h) if step["side"] == "left" else _parent(h, step["hash"])
    return h == expected_root
