"""
routes/process.py — POST /process runs the full pipeline and reports real
numbers for every stage (the Processing screen animates these):

  extract -> resolve (block, score, gate) -> fuse graph -> detect patterns -> seal on chain

GET /stats returns the last run plus live counts for the overview dashboard.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
from collections import Counter

from fastapi import APIRouter

from app import ledger
from app.extract_spans import extract_spans
from app.graph.build import build_graph
from app.graph.overview import communities, persons_graph
from app.resolve import resolve_all
from app.rules import run_alert_rules

router = APIRouter(tags=["pipeline"])
_DB = pathlib.Path(__file__).resolve().parent.parent.parent / "argus.db"


def _extract_all(conn: sqlite3.Connection) -> dict:
    conn.execute("CREATE TABLE IF NOT EXISTS extraction (fir_id TEXT PRIMARY KEY, lang TEXT, "
                 "spans_json TEXT, transliteration TEXT)")
    conn.execute("DELETE FROM extraction")
    names = {}
    for fid, name in conn.execute("SELECT fir_id, name FROM person"):
        names.setdefault(fid, []).append(name)
    by_label, langs = Counter(), Counter()
    for fid, text in conn.execute("SELECT id, narrative FROM fir").fetchall():
        r = extract_spans(text, names.get(fid))
        langs[r["lang"]] += 1
        by_label.update(s["label"] for s in r["spans"])
        conn.execute("INSERT INTO extraction VALUES (?,?,?,?)",
                     (fid, r["lang"], json.dumps(r["spans"], ensure_ascii=False), r["transliteration"]))
    conn.commit()
    return {"firs": sum(langs.values()), "languages": dict(langs), "entities": dict(by_label),
            "total_entities": sum(by_label.values())}


@router.post("/process")
def run_pipeline():
    conn = sqlite3.connect(str(_DB))
    try:
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("fir", "person", "cdr", "bank_txn", "vehicle_reg")}
        extraction = _extract_all(conn)
    finally:
        conn.close()

    resolution = resolve_all(_DB)
    G = build_graph(_DB)
    P = persons_graph(G)
    graph = {"nodes": G.number_of_nodes(), "edges": G.number_of_edges(),
             "by_type": dict(Counter(d["type"] for _, d in G.nodes(data=True))),
             "by_source": dict(Counter(d.get("source") for _, _, d in G.edges(data=True))),
             "communities": len(set(communities(P).values())), "suspects_linked": P.number_of_nodes()}
    alerts = run_alert_rules(_DB)
    alert_stats = {"total": len(alerts), "by_rule": dict(Counter(a["rule"] for a in alerts))}

    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    try:
        masters = conn.execute("SELECT master_id, canonical, members_json FROM master_entity").fetchall()
    finally:
        conn.close()
    items = [("PIPELINE_RUN", {"sources": counts, "extraction": extraction["entities"],
                               "resolution": {k: resolution[k] for k in ("accepted", "review", "rejected", "golden_records")},
                               "alerts": alert_stats["by_rule"]}, "system")]
    items += [("GOLDEN_RECORD", {"master_id": m["master_id"], "name": m["canonical"],
                                 "members": json.loads(m["members_json"])}, "system") for m in masters]
    items += [("ALERT_RAISED", {"rule": a["rule"], "title": a["title"], "entities": a["entities"][:6],
                                "confidence": round(a["confidence"], 3)}, "system") for a in alerts]
    block = ledger.append_many(items)

    stats = {"sources": counts, "extraction": extraction, "resolution": resolution,
             "graph": graph, "alerts": alert_stats, "block": block}
    conn = sqlite3.connect(str(_DB))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS pipeline_state (k TEXT PRIMARY KEY, v TEXT)")
        conn.execute("INSERT OR REPLACE INTO pipeline_state VALUES ('last_run', ?)", (json.dumps(stats),))
        conn.commit()
    finally:
        conn.close()
    return stats


@router.get("/stats")
def get_stats():
    conn = sqlite3.connect(str(_DB))
    try:
        counts = {}
        for t in ("fir", "person", "cdr", "bank_txn", "vehicle_reg", "master_entity", "review_queue", "alerts"):
            try:
                counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.OperationalError:
                counts[t] = 0
        try:
            row = conn.execute("SELECT v FROM pipeline_state WHERE k='last_run'").fetchone()
        except sqlite3.OperationalError:
            row = None
    finally:
        conn.close()
    return {"counts": counts, "last_run": json.loads(row[0]) if row else None}
