"""
chain/verify.py — Independent auditor. Needs only the node files and public
keys; the Argus server does not have to be running.

    python -m app.chain.verify                       # audit all 3 nodes + consensus
    python -m app.chain.verify --evidence bundle.json # prove an exported bundle is on-chain
"""

from __future__ import annotations

import argparse
import json
import sys

from app.chain import NODE_LABELS
from app.chain.crypto import canonical, sha256
from app.chain.merkle import verify_proof
from app.chain.network import nodes, status

G, R, Y, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[1m", "\033[0m"


def audit() -> int:
    st = status()
    c = st["consensus"]
    print(f"{B}Argus Evidence Chain — independent audit{X}")
    for n in st["nodes"]:
        colour = {"in_consensus": G, "out_of_sync": Y, "tampered": R}[n["state"]]
        print(f"  {colour}{'OK ' if n['ok'] else 'BAD'}{X} {NODE_LABELS[n['node']]:<24} "
              f"height={n['height']:<4} entries={n['entries']:<5} head={str(n['head_hash'])[:16]}  "
              f"{colour}{n['state'].upper()}{X}")
        for err in n["errors"][:4]:
            print(f"        {R}- {err}{X}")
    ok = c["quorum"]
    print(f"\n  Consensus: {c['votes']}/{c['total']} nodes agree on head {str(c['head_hash'])[:16]}"
          f"  ->  {(G + 'QUORUM HOLDS') if ok else (R + 'NO QUORUM')}{X}")
    bad = [n for n in st["nodes"] if n["state"] != "in_consensus"]
    if bad:
        print(f"  {Y}Heal with: POST /chain/heal/{bad[0]['node']}  (or the Heal button in the UI){X}")
    return 0 if not bad else 1


def evidence(path: str) -> int:
    bundle = json.loads(open(path, encoding="utf-8").read())
    anchor = bundle.get("anchor") or {}
    if not all(anchor.get(k) for k in ("row_hash", "payload", "merkle_root", "block_hash")):
        print(f"{R}Not an Argus evidence bundle (no chain anchor): {path}{X}")
        return 1
    core ={k: v for k, v in bundle.items() if k not in ("bundle_sha256", "anchor", "ledger_id")}
    steps = []
    digest = sha256(canonical(core))
    steps.append(("Bundle content matches its SHA-256", digest == bundle.get("bundle_sha256")))
    env = json.loads(anchor.get("payload", "{}"))
    steps.append(("Ledger entry records this exact hash", env.get("data", {}).get("bundle_sha256") == digest))
    steps.append(("Entry hash recomputes (prev_hash + payload)",
                  sha256(anchor.get("prev_hash", "") + anchor.get("payload", "")) == anchor.get("row_hash")))
    steps.append(("Merkle proof reaches the block's Merkle root",
                  verify_proof(anchor.get("row_hash", ""), anchor.get("merkle_proof", []), anchor.get("merkle_root", ""))))
    confirmations = 0
    for n in nodes():
        b = next((x for x in n.blocks() if x["height"] == anchor.get("block_height")), None)
        confirmations += bool(b and b["merkle_root"] == anchor.get("merkle_root")
                              and b["block_hash"] == anchor.get("block_hash"))
    steps.append((f"Block header confirmed by {confirmations}/3 agency nodes", confirmations >= 2))
    print(f"{B}Evidence bundle {path}{X}  (alert {bundle.get('alert', {}).get('id')}, "
          f"block {anchor.get('block_height')}, entry #{anchor.get('seq')})")
    for label, ok in steps:
        print(f"  {G + 'PASS' if ok else R + 'FAIL'}{X}  {label}")
    good = all(ok for _, ok in steps)
    print(f"\n  {G + 'AUTHENTIC — unaltered since export' if good else R + 'NOT AUTHENTIC'}{X}")
    return 0 if good else 1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--evidence", help="path to an exported evidence bundle JSON")
    args = ap.parse_args()
    return evidence(args.evidence) if args.evidence else audit()


if __name__ == "__main__":
    raise SystemExit(main())
