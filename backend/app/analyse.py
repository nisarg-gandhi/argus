"""
analyse.py — Graph analytics and rule-based alert generation.

Analytics:
  betweenness_centrality(G, top_k)  -> ranked node list
  degree_centrality(G, top_k)       -> ranked node list

Alert rules (stored in `alerts` table):
  SERIAL_OFFENDER_LINK  — same phone/IMEI/vehicle in FIRs at 2+ stations
  SHARED_DEVICE         — one phone linked to 3+ distinct bank accounts

Alert schema:
  id, rule, entities_json, confidence, source_ids_json, ts

Kept under 150 lines.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import networkx as nx

_HERE   = pathlib.Path(__file__).resolve().parent
DB_PATH = _HERE.parent / "argus.db"


# ════════════════════════════════════════════════════════════════════════════
#  CENTRALITY
# ════════════════════════════════════════════════════════════════════════════

def betweenness_centrality(G: nx.MultiDiGraph, top_k: int = 10) -> list[dict]:
    """Return top-k nodes by betweenness centrality (undirected projection)."""
    ug    = G.to_undirected()
    bc    = nx.betweenness_centrality(ug, normalized=True)
    ranked = sorted(bc.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [
        {"node": nid, "type": G.nodes[nid].get("type", "?"),
         "label": G.nodes[nid].get("label", nid), "score": round(sc, 6)}
        for nid, sc in ranked if nid in G.nodes
    ]


def degree_centrality(G: nx.MultiDiGraph, top_k: int = 10) -> list[dict]:
    """Return top-k nodes by degree centrality (undirected projection)."""
    ug    = G.to_undirected()
    dc    = nx.degree_centrality(ug)
    ranked = sorted(dc.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [
        {"node": nid, "type": G.nodes[nid].get("type", "?"),
         "label": G.nodes[nid].get("label", nid), "score": round(sc, 6)}
        for nid, sc in ranked if nid in G.nodes
    ]


# ════════════════════════════════════════════════════════════════════════════
#  STUB STUBS (kept for router compatibility)
# ════════════════════════════════════════════════════════════════════════════

def shortest_path(G: nx.MultiDiGraph, src: str, dst: str) -> list[str]:
    """Return node-id path from src to dst, or [] if unreachable."""
    try:
        return nx.shortest_path(G.to_undirected(), src, dst)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


def common_neighbours(G: nx.MultiDiGraph, node_id: str, top_k: int = 10) -> list[dict]:
    """Return top-k nodes sharing the most neighbours with *node_id*."""
    if node_id not in G:
        return []
    ug   = G.to_undirected()
    nbrs = set(ug.neighbors(node_id))
    scores: dict[str, int] = defaultdict(int)
    for n in nbrs:
        for nn in ug.neighbors(n):
            if nn != node_id:
                scores[nn] += 1
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [{"node": nid, "shared": cnt,
             "label": G.nodes[nid].get("label", nid)} for nid, cnt in ranked]


def entity_timeline(
    db_path: str | pathlib.Path,
    cluster_ids: list[str],
) -> list[dict]:
    """Collate all events for a resolved cluster, sorted by ts."""
    events: list[dict] = []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        persons = conn.execute(
            f"SELECT id, name, phone FROM person WHERE id IN ({','.join('?'*len(cluster_ids))})",
            cluster_ids,
        ).fetchall()
        phones = [p["phone"] for p in persons if p["phone"]]

        if phones:
            ph_ph = ",".join("?" * len(phones))
            for r in conn.execute(
                f"SELECT 'CDR' AS kind, id, ts, caller, callee FROM cdr "
                f"WHERE caller IN ({ph_ph}) OR callee IN ({ph_ph})",
                phones + phones,
            ):
                events.append(dict(r))
            for r in conn.execute(
                f"SELECT 'TXN' AS kind, id, ts, account_no, amount FROM bank_txn "
                f"WHERE linked_phone IN ({ph_ph})",
                phones,
            ):
                events.append(dict(r))
    finally:
        conn.close()

    events.sort(key=lambda e: e.get("ts", ""))
    return events


# ════════════════════════════════════════════════════════════════════════════
#  ALERT RULES
# ════════════════════════════════════════════════════════════════════════════

def run_alert_rules(
    db_path: str | pathlib.Path = DB_PATH,
) -> list[dict]:
    """Run all rule-based alerts and persist them to the `alerts` table.

    Returns list of generated alert dicts.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    alerts: list[dict] = []
    try:
        _ensure_alerts_table(conn)
        conn.execute("DELETE FROM alerts")  # fresh run each time

        alerts += _rule_serial_offender(conn)
        alerts += _rule_shared_device(conn)

        ts = datetime.now(timezone.utc).isoformat()
        for a in alerts:
            conn.execute(
                "INSERT INTO alerts(rule, entities_json, confidence, source_ids_json, ts) "
                "VALUES (?,?,?,?,?)",
                (a["rule"], json.dumps(a["entities"]),
                 a["confidence"], json.dumps(a["source_ids"]), ts),
            )
        conn.commit()
    finally:
        conn.close()
    return alerts


def _rule_serial_offender(conn: sqlite3.Connection) -> list[dict]:
    """SERIAL_OFFENDER_LINK: same phone/vehicle appears in FIRs at 2+ stations."""
    alerts: list[dict] = []

    # Phone across multiple FIR stations
    rows = conn.execute("""
        SELECT p.phone, GROUP_CONCAT(DISTINCT f.station) AS stations,
               GROUP_CONCAT(DISTINCT p.fir_id) AS fir_ids,
               GROUP_CONCAT(DISTINCT p.id) AS person_ids,
               COUNT(DISTINCT f.station) AS n_stations
        FROM person p
        JOIN fir f ON p.fir_id = f.id
        WHERE p.phone IS NOT NULL AND p.role != 'VICTIM'
        GROUP BY p.phone
        HAVING n_stations >= 2
    """).fetchall()

    for r in rows:
        alerts.append({
            "rule":       "SERIAL_OFFENDER_LINK",
            "entities":   [f"PH:{r['phone']}"] + r["person_ids"].split(","),
            "confidence": min(0.60 + 0.15 * (r["n_stations"] - 2), 0.95),
            "source_ids": r["fir_ids"].split(","),
            "detail":     f"Phone {r['phone']} appears in {r['n_stations']} stations: {r['stations']}",
        })

    # Vehicle reg across multiple FIR stations via person notes
    veh_rows = conn.execute("""
        SELECT p.id, p.notes, p.fir_id, f.station
        FROM person p JOIN fir f ON p.fir_id = f.id
        WHERE p.notes LIKE '%VEH%' OR p.notes LIKE '%UP%' OR p.notes LIKE '%MH%'
    """).fetchall()

    # Group by extracted vehicle reg
    import re
    _RE = re.compile(r"\b([A-Z]{2}\d{1,2}[A-Z]{1,3}\d{1,4})\b", re.IGNORECASE)
    veh_map: dict[str, list[dict]] = defaultdict(list)
    for r in veh_rows:
        for m in _RE.finditer(r["notes"] or ""):
            veh_map[m.group(1).upper()].append(
                {"pid": r["id"], "fir_id": r["fir_id"], "station": r["station"]}
            )

    for reg, occurrences in veh_map.items():
        stations = {o["station"] for o in occurrences}
        if len(stations) >= 2:
            alerts.append({
                "rule":       "SERIAL_OFFENDER_LINK",
                "entities":   [f"VEH:{reg}"] + [o["pid"] for o in occurrences],
                "confidence": min(0.70 + 0.10 * (len(stations) - 2), 0.95),
                "source_ids": list({o["fir_id"] for o in occurrences}),
                "detail":     f"Vehicle {reg} appears in {len(stations)} stations: {', '.join(stations)}",
            })

    return alerts


def _rule_shared_device(conn: sqlite3.Connection) -> list[dict]:
    """SHARED_DEVICE: one phone linked to 3+ distinct bank accounts."""
    alerts: list[dict] = []

    rows = conn.execute("""
        SELECT linked_phone,
               GROUP_CONCAT(DISTINCT account_no) AS accounts,
               GROUP_CONCAT(DISTINCT id)          AS txn_ids,
               COUNT(DISTINCT account_no)         AS n_accts
        FROM bank_txn
        WHERE linked_phone IS NOT NULL
        GROUP BY linked_phone
        HAVING n_accts >= 3
    """).fetchall()

    for r in rows:
        accts  = r["accounts"].split(",")
        alerts.append({
            "rule":       "SHARED_DEVICE",
            "entities":   [f"PH:{r['linked_phone']}"] + [f"ACCT:{a}" for a in accts],
            "confidence": min(0.55 + 0.10 * (r["n_accts"] - 3), 0.90),
            "source_ids": r["txn_ids"].split(","),
            "detail":     f"Phone {r['linked_phone']} linked to {r['n_accts']} accounts: {r['accounts']}",
        })

    return alerts


# ════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _ensure_alerts_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            rule            TEXT NOT NULL,
            entities_json   TEXT NOT NULL,
            confidence      REAL NOT NULL,
            source_ids_json TEXT NOT NULL,
            ts              TEXT NOT NULL
        )
    """)
    conn.commit()
