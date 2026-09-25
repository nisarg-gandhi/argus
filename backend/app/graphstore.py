"""
graphstore.py — In-memory NetworkX graph, rebuilt per request from SQLite.

Node types   : Person | Phone | Account | Vehicle | Location | FIR
Edge types   : OWNS       (Person -> Phone / Account / Vehicle)
               CALLED     (Phone -> Phone, via CDR)
               TRANSFERRED_TO  (Account -> Account, via bank_txn)
               REGISTERED_TO   (Vehicle -> Person)
               NAMED_IN   (Person -> FIR, Person -> Location)

VICTIM nodes are excluded from cross-case traversal when exclude_victims=True.
Resolved entities are collapsed into single master nodes.
"""

from __future__ import annotations

import pathlib
import sqlite3

import networkx as nx

_HERE   = pathlib.Path(__file__).resolve().parent
DB_PATH = _HERE.parent / "argus.db"

LEAF_COLLAPSE_THRESHOLD = 5


def build_graph(
    db_path: str | pathlib.Path = DB_PATH,
    exclude_victims: bool = True,
) -> nx.MultiDiGraph:
    """Read SQLite tables and construct a fresh NetworkX graph."""
    G = nx.MultiDiGraph()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        persons = {
            r["id"]: dict(r)
            for r in conn.execute("SELECT * FROM person").fetchall()
        }
        
        # 1. Map resolved clusters
        golden = conn.execute("SELECT id_a, id_b FROM golden_entities").fetchall()
        temp = nx.Graph()
        temp.add_edges_from([(r["id_a"], r["id_b"]) for r in golden])
        clusters = list(nx.connected_components(temp))
        
        master_map = {}
        for c in clusters:
            nodes = sorted(list(c))
            master_id = nodes[0]
            for n in nodes:
                master_map[n] = master_id
                
        for pid in persons:
            if pid not in master_map:
                master_map[pid] = pid
                
        # Review queue nodes
        review = conn.execute("SELECT id_a, id_b FROM review_queue").fetchall()
        review_nodes = {r["id_a"] for r in review} | {r["id_b"] for r in review}
        victim_ids: set[str] = set()
        
        # 2. Build Person master nodes
        master_nodes = {}
        for pid, p in persons.items():
            if exclude_victims and p["role"] == "VICTIM":
                victim_ids.add(pid)
                continue
                
            mid = master_map[pid]
            if mid not in master_nodes:
                master_nodes[mid] = {
                    "role": p["role"],
                    "fir_id": p["fir_id"],
                    "names": [p["name"]],
                    "in_review": pid in review_nodes
                }
            else:
                if p["name"] not in master_nodes[mid]["names"]:
                    master_nodes[mid]["names"].append(p["name"])
                if pid in review_nodes:
                    master_nodes[mid]["in_review"] = True

        for mid, data in master_nodes.items():
            names = data["names"]
            canonical = sorted(names, key=len, reverse=True)[0]
            aka = [n for n in names if n != canonical]
            
            G.add_node(mid, type="Person", label=canonical,
                       role=data["role"], fir_id=data["fir_id"], aka=aka,
                       dashed=data["in_review"],
                       review_badge="possible match — unreviewed" if data["in_review"] else None)

        # 3. Add edges and connected nodes
        for pid, p in persons.items():
            if pid in victim_ids:
                continue
            mid = master_map[pid]
            
            if p["phone"]:
                ph_id = f"PH:{p['phone']}"
                if not G.has_node(ph_id):
                    G.add_node(ph_id, type="Phone", label=p["phone"])
                G.add_edge(mid, ph_id, etype="OWNS", src=pid)
                
            addr = (p.get("address") or "").strip()
            if addr and addr.lower() not in ("unknown", "unknown — gave mobile only"):
                loc_id = f"LOC:{addr}"
                if not G.has_node(loc_id):
                    G.add_node(loc_id, type="Location", label=addr)
                G.add_edge(mid, loc_id, etype="NAMED_IN", src=pid)
                
        for fir in conn.execute("SELECT id, station FROM fir").fetchall():
            fid = f"FIR:{fir['id']}"
            G.add_node(fid, type="FIR", label=fir["id"], station=fir["station"])
            for p in persons.values():
                if p["id"] in victim_ids: continue
                if p["fir_id"] == fir["id"]:
                    G.add_edge(master_map[p["id"]], fid, etype="NAMED_IN", src=p["id"])
                    
        for v in conn.execute("SELECT * FROM vehicle_reg").fetchall():
            vid = f"VEH:{v['reg_no']}"
            G.add_node(vid, type="Vehicle", label=v["reg_no"], make=v["make"], model=v["model"])
            for p in persons.values():
                if p["id"] in victim_ids: continue
                if p["name"].lower() == v["owner_name"].lower() or (
                    p.get("notes") and v["reg_no"] in (p.get("notes") or "")
                ):
                    G.add_edge(master_map[p["id"]], vid, etype="REGISTERED_TO", src=p["id"])
            G.add_edge(vid, f"OWNER:{v['owner_name']}", etype="REGISTERED_TO", src=vid)
                       
        for cdr in conn.execute("SELECT * FROM cdr").fetchall():
            src_id  = f"PH:{cdr['caller']}"
            dst_id  = f"PH:{cdr['callee']}"
            if not G.has_node(src_id): G.add_node(src_id, type="Phone", label=cdr["caller"])
            if not G.has_node(dst_id): G.add_node(dst_id, type="Phone", label=cdr["callee"])
            G.add_edge(src_id, dst_id, etype="CALLED", ts=cdr["ts"], dur=cdr["duration_s"], tower=cdr["tower_loc"], cdr_id=cdr["id"])
                       
        acct_phone: dict[str, str] = {}
        for txn in conn.execute("SELECT * FROM bank_txn").fetchall():
            acct_id = f"ACCT:{txn['account_no']}"
            if not G.has_node(acct_id):
                G.add_node(acct_id, type="Account", label=txn["account_no"], holder=txn["holder_name"])
            if txn["linked_phone"]:
                acct_phone[txn["account_no"]] = txn["linked_phone"]
            if txn["txn_type"] == "TRANSFER" and txn["counterpart"]:
                dst_acct = f"ACCT:{txn['counterpart']}"
                if not G.has_node(dst_acct): G.add_node(dst_acct, type="Account", label=txn["counterpart"])
                G.add_edge(acct_id, dst_acct, etype="TRANSFERRED_TO", ts=txn["ts"], amount=txn["amount"], txn_id=txn["id"])

        for acct_no, phone in acct_phone.items():
            ph_id, acct_id = f"PH:{phone}", f"ACCT:{acct_no}"
            if not G.has_node(ph_id): G.add_node(ph_id, type="Phone", label=phone)
            G.add_edge(acct_id, ph_id, etype="OWNS", src=acct_id)

    finally:
        conn.close()

    return G


def get_subgraph(
    master_id: str,
    hops: int = 2,
    db_path: str | pathlib.Path = DB_PATH,
    exclude_victims: bool = True,
) -> nx.MultiDiGraph:
    """Return the ego-graph around *master_id* within *hops* hops, collapsing leaves."""
    G = build_graph(db_path, exclude_victims=exclude_victims)
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    alert_entities = set()
    try:
        golden = conn.execute("SELECT id_a, id_b FROM golden_entities").fetchall()
        temp = nx.Graph()
        temp.add_edges_from([(r["id_a"], r["id_b"]) for r in golden])
        clusters = list(nx.connected_components(temp))
        for c in clusters:
            if master_id in c:
                master_id = sorted(list(c))[0]
                break
                
        try:
            alerts = conn.execute("SELECT entities_json FROM alerts").fetchall()
            import json
            for r in alerts:
                for eid in json.loads(r["entities_json"]):
                    alert_entities.add(eid)
        except sqlite3.OperationalError:
            pass
    finally:
        conn.close()

    if master_id not in G:
        return nx.MultiDiGraph()
            
    undirected = G.to_undirected(as_view=True)
    ego        = nx.ego_graph(undirected, master_id, radius=hops)
    sub        = G.subgraph(ego.nodes).copy()
    
    # Precompute full-graph degrees
    full_degrees = dict(undirected.degree())
    
    # Priority 1: master_id, connected via OWNS/REGISTERED_TO to master_id, in alerts
    p1 = {master_id} | alert_entities
    for u, v, d in sub.edges(data=True):
        if d.get("etype") in ("OWNS", "REGISTERED_TO"):
            if u == master_id: p1.add(v)
            if v == master_id: p1.add(u)
            
    # Priority 2: aka list non-empty
    p2 = set()
    for n, d in sub.nodes(data=True):
        if d.get("aka"):
            p2.add(n)
            
    # Collapse Priority 3 leaves
    nodes_to_remove = set()
    summary_nodes_to_add = []
    
    from collections import defaultdict
    for n in list(sub.nodes()):
        if n in nodes_to_remove:
            continue
            
        # Group Priority 3 full-graph leaves connected by same-type edges
        leaves_by_etype = defaultdict(list)
        # Check out-edges
        for _, v, key, edata in sub.out_edges(n, data=True, keys=True):
            if v not in p1 and v not in p2 and full_degrees.get(v) == 1:
                leaves_by_etype[edata.get("etype", "UNKNOWN")].append((v, key, edata, "out"))
        # Check in-edges
        for u, _, key, edata in sub.in_edges(n, data=True, keys=True):
            if u not in p1 and u not in p2 and full_degrees.get(u) == 1:
                leaves_by_etype[edata.get("etype", "UNKNOWN")].append((u, key, edata, "in"))
                
        for etype, leaves in leaves_by_etype.items():
            # Remove duplicates if it's a MultiDiGraph and both directions exist, though unlikely for degree=1
            unique_leaves = {}
            for leaf, key, edata, direction in leaves:
                if leaf not in unique_leaves:
                    unique_leaves[leaf] = (key, edata, direction)
                    
            if len(unique_leaves) > LEAF_COLLAPSE_THRESHOLD:
                children = []
                for leaf, (key, edata, direction) in unique_leaves.items():
                    nodes_to_remove.add(leaf)
                    leaf_data = sub.nodes[leaf].copy()
                    leaf_data["id"] = leaf
                    edge_obj = {"from": n if direction == "out" else leaf,
                                "to": leaf if direction == "out" else n,
                                "type": edata.get("etype"),
                                "label": edata.get("etype")}
                    edge_obj.update(edata)
                    children.append({"node": leaf_data, "edge": edge_obj})
                
                children.sort(key=lambda x: x["node"]["id"])
                
                sum_id = f"COLLAPSED:{n}:{etype}"
                summary_nodes_to_add.append({
                    "id": sum_id,
                    "parent": n,
                    "etype": etype,
                    "count": len(unique_leaves),
                    "children": children
                })
                
    for n in nodes_to_remove:
        sub.remove_node(n)
        
    for n in sub.nodes():
        if n in alert_entities:
            sub.nodes[n]["alert"] = True
            
    import json
    for s in summary_nodes_to_add:
        sub.add_node(s["id"], type="Summary", label=f"+{s['count']} more {s['etype']}s", children=s["children"])
        # Add edge from parent to summary node
        sub.add_edge(s["parent"], s["id"], etype=s["etype"], label=f"+{s['count']} more {s['etype']}s")
        
    return sub
