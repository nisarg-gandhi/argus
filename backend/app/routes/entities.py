"""
routes/entities.py — GET /entities?q=
Search persons, phones, vehicles, accounts across all source tables.
"""

from __future__ import annotations

import pathlib
import sqlite3

from fastapi import APIRouter, Query
from rapidfuzz import fuzz

from app.er.normalise import display_name

router = APIRouter(tags=["entities"])

_DB = pathlib.Path(__file__).resolve().parent.parent.parent / "argus.db"


@router.get("/entities")
def search_entities(q: str = Query(..., min_length=1, description="Search term")):
    """Full-text search across persons, phones, vehicles, accounts.

    Returns up to 50 results ranked by fuzzy relevance.
    """
    term = q.strip().lower()
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    results: list[dict] = []

    try:
        # Persons
        for r in conn.execute("SELECT id, name, alias, role, phone, address, fir_id FROM person "
                              "WHERE role != 'VICTIM'"):      # victims are never searchable
            score = max(
                fuzz.partial_ratio(term, (r["name"] or "").lower()),
                fuzz.partial_ratio(term, display_name(r["name"] or "").lower()),
                fuzz.partial_ratio(term, (r["alias"] or "").lower()),
                fuzz.partial_ratio(term, (r["phone"] or "").lower()),
                fuzz.partial_ratio(term, (r["address"] or "").lower()),
            )
            if score >= 60:
                results.append({
                    "type": "Person", "id": r["id"],
                    "label": r["name"], "role": r["role"], "latin": display_name(r["name"]),
                    "phone": r["phone"], "fir_id": r["fir_id"],
                    "relevance": score,
                })

        # Vehicles
        for r in conn.execute("SELECT id, reg_no, owner_name, make, model FROM vehicle_reg"):
            score = max(
                fuzz.partial_ratio(term, (r["reg_no"] or "").lower()),
                fuzz.partial_ratio(term, (r["owner_name"] or "").lower()),
            )
            if score >= 60:
                results.append({
                    "type": "Vehicle", "id": r["id"],
                    "label": r["reg_no"], "owner": r["owner_name"],
                    "make": r["make"], "model": r["model"],
                    "relevance": score,
                })

        # Bank accounts
        for r in conn.execute(
            "SELECT DISTINCT account_no, holder_name, linked_phone FROM bank_txn"
        ):
            score = max(
                fuzz.partial_ratio(term, (r["account_no"] or "").lower()),
                fuzz.partial_ratio(term, (r["holder_name"] or "").lower()),
            )
            if score >= 60:
                results.append({
                    "type": "Account", "id": f"ACCT:{r['account_no']}",
                    "label": r["account_no"], "holder": r["holder_name"],
                    "phone": r["linked_phone"],
                    "relevance": score,
                })

        # CDR phones (distinct callers matching term)
        for r in conn.execute("SELECT DISTINCT caller FROM cdr"):
            if term in r["caller"]:
                results.append({
                    "type": "Phone", "id": f"PH:{r['caller']}",
                    "label": r["caller"], "relevance": 80,
                })

    finally:
        conn.close()

    # Deduplicate by id and sort by relevance
    seen: set[str] = set()
    unique: list[dict] = []
    for r in sorted(results, key=lambda x: x["relevance"], reverse=True):
        if r["id"] not in seen:
            seen.add(r["id"])
            unique.append(r)

    return {"query": q, "results": unique[:50], "total": len(unique)}
