"""
graph/build.py — Fuse all five sources into one knowledge graph.

Node types : Person | Phone | Account | Vehicle | Location | FIR
Every edge carries `source` (FIR / CDR / BANK / RTO) so the UI can show which
department's data produced each link. Calls and transfers are aggregated per
pair (count, volume, first/last seen) instead of thousands of parallel edges.

resolved=True collapses person records into golden records (master ids);
resolved=False keeps every raw record separate ("before resolution" view).
VICTIM persons are never nodes; their phones/accounts are masked.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sqlite3
from collections import defaultdict

import networkx as nx

from app.datagen.pools import LOCALITIES
from app.er.golden import ensure_tables, master_map
from app.er.normalise import display_name, localities

DB_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "argus.db"


def _mask(v: str) -> str:
    return v[:2] + "•" * (len(v) - 5) + v[-3:] if v and len(v) > 5 else "•••"


def _pid(prefix: str, value: str, protected: bool) -> str:
    """Victim identifiers get an opaque node id so the raw number never leaves the server."""
    return f"{prefix}:V-{hashlib.sha256(value.encode()).hexdigest()[:10]}" if protected else f"{prefix}:{value}"


def build_graph(db_path=DB_PATH, resolved: bool = True) -> nx.MultiDiGraph:
    G = nx.MultiDiGraph()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        ensure_tables(conn)
        persons = [dict(r) for r in conn.execute("SELECT p.*, f.station, f.date FROM person p JOIN fir f ON f.id=p.fir_id")]
        victims = [p for p in persons if p["role"] == "VICTIM"]
        people = [p for p in persons if p["role"] != "VICTIM"]
        mm = master_map(conn) if resolved else {}
        masters = {r["master_id"]: dict(r) for r in conn.execute("SELECT * FROM master_entity")} if resolved else {}
        review_ids = {x for r in conn.execute("SELECT id_a, id_b FROM review_queue") for x in r}
        protected_phones = {p["phone"] for p in victims if p["phone"]}
        protected_accts = {p["account_no"] for p in victims if p["account_no"]}

        def phone_node(ph: str) -> str:
            prot = ph in protected_phones
            nid = _pid("PH", ph, prot)
            if nid not in G:
                G.add_node(nid, type="Phone", label=_mask(ph) if prot else ph, protected=prot)
            return nid

        def acct_node(ac: str, holder: str = "") -> str:
            prot = ac in protected_accts
            nid = _pid("ACCT", ac, prot)
            if nid not in G:
                G.add_node(nid, type="Account", label=_mask(ac) if prot else ac,
                           holder="Protected (victim)" if prot else holder, protected=prot)
            elif holder and not G.nodes[nid].get("holder") and not prot:
                G.nodes[nid]["holder"] = holder
            return nid

        # ── Persons (golden records or raw records) + FIR-sourced links ──
        for p in people:
            mid = mm.get(p["id"], p["id"])
            if mid not in G:
                m = masters.get(mid)
                G.add_node(mid, type="Person", role=p["role"],
                           label=m["canonical"] if m else display_name(p["name"]) or p["name"],
                           raw_name=p["name"], records=json.loads(m["members_json"]) if m else [p["id"]],
                           aka=[n for n in json.loads(m["names_json"]) if display_name(n) != m["canonical"]] if m else [],
                           stations=json.loads(m["stations_json"]) if m else [p["station"]],
                           merged=bool(m), in_review=False)
            if p["id"] in review_ids:
                G.nodes[mid]["in_review"] = True
            fid = f"FIR:{p['fir_id']}"
            if fid not in G:
                G.add_node(fid, type="FIR", label=p["fir_id"], station=p["station"], date=p["date"])
            G.add_edge(mid, fid, etype="NAMED_IN", source="FIR", record=p["id"])
            for field, etype, make in (("phone", "OWNS", phone_node), ("account_no", "OWNS", acct_node)):
                if p[field]:
                    G.add_edge(mid, make(p[field]), etype=etype, source="FIR", record=p["id"])
            if p["vehicle"]:
                vid = f"VEH:{p['vehicle']}"
                if vid not in G:
                    G.add_node(vid, type="Vehicle", label=p["vehicle"])
                G.add_edge(mid, vid, etype="SEEN_WITH", source="FIR", record=p["id"])
            for loc in localities(p["address"] or "") & set(LOCALITIES):
                G.add_node(f"LOC:{loc}", type="Location", label=loc)
                G.add_edge(mid, f"LOC:{loc}", etype="LIVES_IN", source="FIR", record=p["id"])

        # ── RTO: vehicle registrations (owner name -> person when unambiguous) ──
        owners = defaultdict(set)
        for p in people:
            owners[display_name(p["name"]).lower()].add(mm.get(p["id"], p["id"]))
        for v in conn.execute("SELECT * FROM vehicle_reg"):
            vid = f"VEH:{v['reg_no']}"
            match = owners.get(display_name(v["owner_name"]).lower(), set())
            if vid in G or len(match) == 1:
                G.add_node(vid, type="Vehicle", label=v["reg_no"], make=v["make"], model=v["model"],
                           colour=v["colour"], owner=v["owner_name"])
                if len(match) == 1:
                    G.add_edge(vid, next(iter(match)), etype="REGISTERED_TO", source="RTO")

        # ── CDR: aggregated call links ──
        for r in conn.execute("SELECT caller, callee, COUNT(*) n, SUM(duration_s) dur, MIN(ts) first, "
                              "MAX(ts) last FROM cdr GROUP BY caller, callee"):
            G.add_edge(phone_node(r["caller"]), phone_node(r["callee"]), etype="CALLED", source="CDR",
                       count=r["n"], duration_s=r["dur"], first=r["first"], last=r["last"])

        # ── BANK: KYC phone links + aggregated transfers ──
        for r in conn.execute("SELECT DISTINCT account_no, holder_name, linked_phone FROM bank_txn"):
            a = acct_node(r["account_no"], r["holder_name"])
            if r["linked_phone"]:
                G.add_edge(a, phone_node(r["linked_phone"]), etype="KYC_PHONE", source="BANK")
        for r in conn.execute("SELECT account_no, counterpart, COUNT(*) n, SUM(amount) amt, MIN(ts) first, "
                              "MAX(ts) last FROM bank_txn WHERE txn_type='TRANSFER' AND counterpart GLOB '[0-9]*' "
                              "GROUP BY account_no, counterpart"):
            G.add_edge(acct_node(r["account_no"]), acct_node(r["counterpart"]), etype="TRANSFERRED_TO",
                       source="BANK", count=r["n"], amount=round(r["amt"], 2), first=r["first"], last=r["last"])
        G.graph["victims_excluded"] = len(victims)
    finally:
        conn.close()
    return G

