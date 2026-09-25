"""
graph/views.py — Focused views over the knowledge graph.

ego()   : n-hop neighbourhood of an entity. Location nodes are shown but never
          expanded through (everyone in Aminabad is not "connected").
          Bulky leaves (e.g. 40 one-off numbers a phone called) are collapsed
          into a single "+40 more" node the analyst can expand on click.
path()  : shortest chain of evidence between two entities.
"""

from __future__ import annotations

from collections import defaultdict

import networkx as nx

HUBS = {"Location"}
COLLAPSIBLE = {"Phone", "Account"}
COLLAPSE_OVER = 4


def ego(G: nx.MultiDiGraph, center: str, hops: int = 2) -> nx.MultiDiGraph:
    U = G.to_undirected(as_view=True)
    seen, frontier = {center: 0}, [center]
    for d in range(1, hops + 1):
        nxt = []
        for n in frontier:
            if n != center and G.nodes[n].get("type") in HUBS:
                continue
            for m in U.neighbors(n):
                if m not in seen:
                    seen[m] = d
                    nxt.append(m)
        frontier = nxt
    sub = G.subgraph(seen).copy()
    for n, d in seen.items():
        sub.nodes[n]["hop"] = d
    return _collapse(sub, keep={center})


def _collapse(sub: nx.MultiDiGraph, keep: set[str]) -> nx.MultiDiGraph:
    U = sub.to_undirected(as_view=True)
    groups: dict[tuple, list[tuple]] = defaultdict(list)
    for n in list(sub.nodes):
        if n in keep or sub.nodes[n].get("type") not in COLLAPSIBLE or U.degree(n) != 1:
            continue
        parent = next(iter(U.neighbors(n)))
        key, edge = (parent, None), None
        for u, v, data in sub.edges(data=True):
            if n in (u, v):
                key, edge = (parent, data.get("etype")), (u, v, data)
                break
        groups[key].append((n, edge))
    for (parent, etype), leaves in groups.items():
        if len(leaves) <= COLLAPSE_OVER:
            continue
        children = [{"node": {"id": n, **sub.nodes[n]},
                     "edge": {"from": u, "to": v, **d}} for n, (u, v, d) in leaves]
        sub.remove_nodes_from([n for n, _ in leaves])
        sid = f"COLLAPSED:{parent}:{etype}"
        sub.add_node(sid, type="Summary", label=f"+{len(leaves)} more", children=children,
                     etype=etype, hop=sub.nodes[parent].get("hop", 0) + 1)
        sub.add_edge(parent, sid, etype=etype, source=children[0]["edge"].get("source", ""))
    return sub


def path(G: nx.MultiDiGraph, src: str, dst: str) -> list[str]:
    """Shortest evidence chain ignoring Location hubs; [] if unconnected."""
    keep = [n for n, d in G.nodes(data=True) if d.get("type") not in HUBS]
    U = G.subgraph(keep).to_undirected(as_view=True)
    try:
        return nx.shortest_path(U, src, dst)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


def path_subgraph(G: nx.MultiDiGraph, nodes: list[str]) -> nx.MultiDiGraph:
    """Only the nodes on the path and the edges linking consecutive hops."""
    sub = nx.MultiDiGraph()
    for i, n in enumerate(nodes):
        sub.add_node(n, **G.nodes[n], hop=i)
    for a, b in zip(nodes, nodes[1:]):
        for u, v in ((a, b), (b, a)):
            for data in (G.get_edge_data(u, v) or {}).values():
                sub.add_edge(u, v, **data)
    return sub
