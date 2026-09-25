"""
routes/graph.py — Graph API for the vis-network frontend.

  GET /graph/overview?level=persons|entities   whole network, gangs coloured
  GET /graph/path?src=&dst=                    shortest evidence chain
  GET /graph/{node_id}?hops=2&resolved=true    ego network (before/after ER)
  GET /analytics/key-players                   betweenness-ranked brokers
"""

from __future__ import annotations

import json
import pathlib
import sqlite3

import networkx as nx
from fastapi import APIRouter, HTTPException, Query

from app.graph.build import build_graph
from app.graph.overview import communities, key_players, persons_graph
from app.graph.views import ego, path, path_subgraph

router = APIRouter(tags=["graph"])
_DB = pathlib.Path(__file__).resolve().parent.parent.parent / "argus.db"
_NODE_KEYS = ("type", "label", "role", "hop", "merged", "in_review", "protected", "holder",
              "station", "date", "make", "model", "owner", "stations", "aka", "records", "children")


def _alert_entities() -> set[str]:
    conn = sqlite3.connect(str(_DB))
    try:
        return {e for (js,) in conn.execute("SELECT entities_json FROM alerts") for e in json.loads(js)}
    except sqlite3.OperationalError:
        return set()
    finally:
        conn.close()


def _resolve_id(G: nx.MultiDiGraph, node_id: str) -> str:
    if node_id in G:
        return node_id
    for n, d in G.nodes(data=True):                      # a raw record id -> its golden record
        if node_id in (d.get("records") or []):
            return n
    raise HTTPException(404, f"Node '{node_id}' not found in graph")


def to_vis(sub: nx.MultiDiGraph, extra: dict[str, dict] | None = None) -> dict:
    alerts, extra = _alert_entities(), extra or {}
    nodes = []
    for n, d in sub.nodes(data=True):
        node = {"id": n, **{k: d[k] for k in _NODE_KEYS if d.get(k) not in (None, [], "")}}
        node["alert"] = n in alerts or any(r in alerts for r in d.get("records") or [])
        node.update(extra.get(n, {}))
        nodes.append(node)
    edges = [{"id": i, "from": u, "to": v, **{k: d[k] for k in
              ("etype", "source", "count", "amount", "duration_s", "first", "last") if d.get(k) is not None}}
             for i, (u, v, d) in enumerate(sub.edges(data=True))]
    return {"nodes": nodes, "edges": edges}


@router.get("/graph/overview")
def overview(level: str = Query("persons", pattern="^(persons|entities)$")):
    G = build_graph(_DB)
    P = persons_graph(G)
    comm = communities(P)
    bc = nx.betweenness_centrality(P) if P.number_of_nodes() else {}
    if level == "persons":
        sub = nx.MultiDiGraph()
        sub.add_nodes_from((n, G.nodes[n]) for n in P.nodes)
        for a, b, e in P.edges(data=True):
            sub.add_edge(a, b, etype=" + ".join(sorted(e["kinds"])), count=e["calls"] or None,
                         amount=round(e["amount"], 2) or None, source="FUSED")
    else:
        owned = {v for u, v, d in G.edges(data=True) if d["etype"] in ("OWNS", "KYC_PHONE")}
        keep = [n for n, d in G.nodes(data=True) if d["type"] != "Location"
                and (d["type"] not in ("Phone", "Account") or n in owned)]
        sub = G.subgraph(keep).copy()
        sub.remove_nodes_from([n for n in list(sub) if sub.degree(n) == 0])
        U = nx.Graph(sub.to_undirected())
        comm = {n: i for i, c in enumerate(sorted(nx.community.louvain_communities(U, seed=7), key=len, reverse=True))
                for n in c}
        bc = {n: d / max(len(U) - 1, 1) for n, d in U.degree()}
    extra = {n: {"community": comm.get(n), "centrality": round(bc.get(n, 0), 4)} for n in sub.nodes}
    out = to_vis(sub, extra)
    out.update({"level": level, "communities": len(set(comm.values())),
                "victims_excluded": G.graph.get("victims_excluded", 0),
                "totals": {"nodes": G.number_of_nodes(), "edges": G.number_of_edges()}})
    return out


@router.get("/analytics/key-players")
def get_key_players(top_k: int = 8):
    return {"key_players": key_players(persons_graph(build_graph(_DB)), top_k)}


@router.get("/graph/path")
def get_path(src: str, dst: str):
    G = build_graph(_DB)
    nodes = path(G, _resolve_id(G, src), _resolve_id(G, dst))
    if not nodes:
        return {"found": False, "nodes": [], "edges": [], "hops": 0}
    owners = {}
    for n in nodes:
        people = [G.nodes[p]["label"] for p in G.predecessors(n)
                  if G.nodes[p].get("type") == "Person" and any(
                      d.get("etype") == "OWNS" for d in G.get_edge_data(p, n).values())]
        if people:
            owners[n] = {"owner": ", ".join(people)}
    return {"found": True, "hops": len(nodes) - 1, "path": nodes, **to_vis(path_subgraph(G, nodes), owners)}


@router.get("/graph/{node_id}")
def get_graph(node_id: str, hops: int = Query(2, ge=1, le=4), resolved: bool = True):
    G = build_graph(_DB, resolved=resolved)
    center = _resolve_id(G, node_id)
    sub = ego(G, center, hops)
    out = to_vis(sub)
    out.update({"center": center, "hops": hops, "resolved": resolved,
                "victims_excluded": G.graph.get("victims_excluded", 0)})
    return out
