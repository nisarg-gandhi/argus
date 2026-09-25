"""
routes/resolution.py — Read-side of entity resolution and extraction.

  GET /resolution/golden     golden records (master IDs) with their source records
  GET /resolution/pairs      every scored pair + factor-level evidence (match graph)
  GET /node/{node_id}        side-panel details for any graph node
  GET /extract               FIR list with language + entity counts
  GET /extract/{fir_id}      narrative with highlighted entity spans
"""

from __future__ import annotations

import json
import pathlib
import sqlite3

from fastapi import APIRouter, HTTPException

from app.er.golden import ensure_tables
from app.er.normalise import display_name
from app.graph import details

router = APIRouter(tags=["resolution"])
_DB = pathlib.Path(__file__).resolve().parent.parent.parent / "argus.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    ensure_tables(conn)
    return conn


@router.get("/resolution/golden")
def golden_records():
    conn = _conn()
    try:
        out = []
        for m in conn.execute("SELECT * FROM master_entity ORDER BY n_records DESC, canonical"):
            members = json.loads(m["members_json"])
            ph = ",".join("?" * len(members))
            recs = [dict(r) for r in conn.execute(
                f"SELECT p.id, p.name, p.alias, p.phone, p.vehicle, p.imei, p.account_no, p.fir_id, "
                f"f.station, f.date FROM person p JOIN fir f ON f.id=p.fir_id WHERE p.id IN ({ph}) "
                f"ORDER BY f.date", members)]
            via = {r[0] for r in conn.execute(
                f"SELECT via FROM golden_entities WHERE id_a IN ({ph})", members)}
            out.append({"master_id": m["master_id"], "canonical": m["canonical"], "role": m["role"],
                        "n_records": m["n_records"], "names": json.loads(m["names_json"]),
                        "identifiers": json.loads(m["identifiers_json"]),
                        "stations": json.loads(m["stations_json"]), "records": recs,
                        "human_confirmed": "human" in via})
        return {"golden": out, "count": len(out)}
    finally:
        conn.close()


@router.get("/resolution/pairs")
def match_pairs():
    conn = _conn()
    try:
        people = {r["id"]: r for r in conn.execute("SELECT id, name, role, fir_id FROM person")}
        pairs = []
        for r in conn.execute("SELECT * FROM match_pairs ORDER BY score DESC"):
            a, b = people[r["id_a"]], people[r["id_b"]]
            pairs.append({"id": r["id"], "a": r["id_a"], "b": r["id_b"], "name_a": a["name"], "name_b": b["name"],
                          "latin_a": display_name(a["name"]), "latin_b": display_name(b["name"]),
                          "score": r["score"], "decision": r["decision"],
                          "blocks": json.loads(r["blocks_json"]), "evidence": json.loads(r["evidence_json"])})
        return {"pairs": pairs, "count": len(pairs)}
    finally:
        conn.close()


@router.get("/node/{node_id}")
def node_details(node_id: str):
    conn = _conn()
    try:
        return details.lookup(conn, node_id)
    finally:
        conn.close()


@router.get("/extract")
def list_extractions():
    conn = _conn()
    try:
        rows = conn.execute("SELECT f.id, f.station, f.date, f.section, e.lang, e.spans_json FROM fir f "
                            "LEFT JOIN extraction e ON e.fir_id=f.id ORDER BY (e.lang='hi') DESC, f.date").fetchall()
    except sqlite3.OperationalError:
        return {"firs": []}
    finally:
        conn.close()
    return {"firs": [{"id": r["id"], "station": r["station"], "date": r["date"], "section": r["section"],
                      "lang": r["lang"], "n_entities": len(json.loads(r["spans_json"] or "[]"))} for r in rows]}


@router.get("/extract/{fir_id}")
def get_extraction(fir_id: str):
    conn = _conn()
    try:
        f = conn.execute("SELECT * FROM fir WHERE id=?", (fir_id,)).fetchone()
        e = conn.execute("SELECT * FROM extraction WHERE fir_id=?", (fir_id,)).fetchone()
    finally:
        conn.close()
    if not f:
        raise HTTPException(404, f"FIR {fir_id} not found")
    return {**dict(f), "lang": e["lang"] if e else None, "spans": json.loads(e["spans_json"]) if e else [],
            "transliteration": e["transliteration"] if e else None}
