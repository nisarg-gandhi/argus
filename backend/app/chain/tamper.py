"""
chain/tamper.py — Simulate a malicious insider editing ONE node's database
file directly, bypassing the Argus application entirely (raw sqlite3 only).

    python -m app.chain.tamper --node forensic_lab              # naive edit
    python -m app.chain.tamper --node forensic_lab --rehash     # cover tracks

--rehash also recomputes every hash, Merkle root and block link after the
edit, so the local hash chain looks consistent. It still gets caught: the
insider cannot forge the officers' Ed25519 signatures, and the other two
agencies' copies out-vote the altered one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys

from app.chain import DATA_DIR, NODES


def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _canon(o) -> str:
    return json.dumps(o, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def _merkle(leaves: list[str]) -> str:
    level = leaves or [_h("")]
    while len(level) > 1:
        level = [_h(level[i] + (level[i + 1] if i + 1 < len(level) else level[i]))
                 for i in range(0, len(level), 2)]
    return level[0]


def _mutate(data: dict) -> str:
    if "decision" in data:
        old = data["decision"]
        data["decision"] = "reject" if old == "accept" else "accept"
        return f"decision '{old}' -> '{data['decision']}'"
    if "verdict" in data:
        old, data["verdict"] = data["verdict"], "fp"
        return f"verdict '{old}' -> 'fp'"
    for k in ("bundle_sha256", "sha256"):
        if k in data:
            data[k] = "f" * 64
            return f"{k} replaced with a forged hash"
    data["note"] = "record altered by insider"
    return "inserted a forged field"


def run(node: str, seq: int | None = None, rehash: bool = False) -> list[str]:
    """Edit one entry in *node*'s database file directly. Returns a log of what was done."""
    db = DATA_DIR / node / "node.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        seq = seq or (conn.execute(
            "SELECT seq FROM entries WHERE action IN ('REVIEW_DECISION','FEEDBACK','EXPORT','INGEST_FILE') "
            "ORDER BY seq DESC LIMIT 1").fetchone() or conn.execute(
            "SELECT MAX(seq) AS seq FROM entries").fetchone())["seq"]
        row = conn.execute("SELECT * FROM entries WHERE seq=?", (seq,)).fetchone()
        env = json.loads(row["payload"])
        what = _mutate(env["data"])
        conn.execute("UPDATE entries SET payload=? WHERE seq=?", (_canon(env), seq))
        log = [f"[insider] {db}", f"[insider] entry #{seq} ({row['action']}, block {row['block_height']}): {what}"]
        if rehash:
            _rehash(conn, seq)
            log.append("[insider] recomputed row hashes, Merkle roots and block hashes to hide the edit")
        conn.commit()
    finally:
        conn.close()
    return log + ["[insider] done. Now run:  python -m app.chain.verify"]


def _rehash(conn: sqlite3.Connection, seq: int) -> None:
    prev = None
    for e in conn.execute("SELECT seq, payload, prev_hash, row_hash FROM entries ORDER BY seq").fetchall():
        if e["seq"] < seq:
            prev = e["row_hash"]
            continue
        p = prev if prev is not None else e["prev_hash"]
        prev = _h(p + e["payload"])
        conn.execute("UPDATE entries SET prev_hash=?, row_hash=? WHERE seq=?", (p, prev, e["seq"]))
    prev_block = None
    keys = ["height", "ts", "prev_block_hash", "merkle_root", "first_seq", "n_entries", "proposer"]
    for b in conn.execute("SELECT * FROM blocks ORDER BY height").fetchall():
        hdr = dict(b)
        if prev_block is not None:
            hdr["prev_block_hash"] = prev_block
        hdr["merkle_root"] = _merkle([r[0] for r in conn.execute(
            "SELECT row_hash FROM entries WHERE block_height=? ORDER BY seq", (b["height"],))])
        hdr["block_hash"] = _h(_canon({k: hdr[k] for k in keys}))
        conn.execute("UPDATE blocks SET prev_block_hash=?, merkle_root=?, block_hash=? WHERE height=?",
                     (hdr["prev_block_hash"], hdr["merkle_root"], hdr["block_hash"], b["height"]))
        prev_block = hdr["block_hash"]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--node", choices=NODES, default="forensic_lab")
    ap.add_argument("--seq", type=int, help="entry to alter (default: latest decision/evidence entry)")
    ap.add_argument("--rehash", action="store_true", help="recompute hashes to hide the edit")
    args = ap.parse_args()
    for line in run(args.node, args.seq, args.rehash):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
