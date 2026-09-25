"""
graph/overview.py — Whole-network views and key-player analytics.

persons_graph() projects the knowledge graph onto people: two suspects are
linked if their phones called each other, money moved between accounts they
control, they were named in the same FIR, or they share an identifier.
Louvain finds the gangs; betweenness finds the brokers who hold them together
(centrality predicts judicial outcomes on real networks — Masías et al., ref 7).
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations

import networkx as nx

OWNERSHIP = {"OWNS", "SEEN_WITH", "REGISTERED_TO"}


def _owners(G: nx.MultiDiGraph) -> dict[str, set[str]]:
    own: dict[str, set[str]] = defaultdict(set)
    for u, v, d in G.edges(data=True):
        if d.get("etype") in OWNERSHIP:
            person, thing = (u, v) if G.nodes[u].get("type") == "Person" else (v, u)
            own[thing].add(person)
    for u, v, d in G.edges(data=True):                   # bank KYC: account follows its phone
        if d.get("etype") == "KYC_PHONE":
            own[u] |= own.get(v, set())
    return own


def persons_graph(G: nx.MultiDiGraph) -> nx.Graph:
    own = _owners(G)
    P = nx.Graph()

    def link(a, b, kind, weight, **extra):
        if a == b:
            return
        if not P.has_edge(a, b):
            P.add_edge(a, b, weight=0, kinds=set(), calls=0, amount=0.0, shared=[])
        e = P[a][b]
        e["weight"] += weight
        e["kinds"].add(kind)
        for k, v in extra.items():
            e[k] = e[k] + v if isinstance(v, (int, float)) else e[k] + [v]

    for u, v, d in G.edges(data=True):
        if d.get("etype") == "CALLED":
            for a in own.get(u, ()):
                for b in own.get(v, ()):
                    link(a, b, "calls", min(d["count"], 20) / 4, calls=d["count"])
        elif d.get("etype") == "TRANSFERRED_TO":
            for a in own.get(u, ()):
                for b in own.get(v, ()):
                    link(a, b, "money", 3, amount=d["amount"])
    for n, data in G.nodes(data=True):
        if data.get("type") == "FIR":
            accused = [p for p in G.predecessors(n) if G.nodes[p].get("role") == "ACCUSED"]
            for a, b in combinations(sorted(set(accused)), 2):
                link(a, b, "co-accused", 4)
        elif len(own.get(n, ())) > 1 and data.get("type") in ("Phone", "Vehicle", "Account"):
            for a, b in combinations(sorted(own[n]), 2):
                link(a, b, f"shared {data['type'].lower()}", 3, shared=data.get("label", n))
    for n in list(P.nodes):
        P.nodes[n].update({k: G.nodes[n].get(k) for k in ("label", "role", "merged", "stations", "records", "in_review")})
    return P


def communities(P: nx.Graph) -> dict[str, int]:
    if not P.number_of_nodes():
        return {}
    comms = nx.community.louvain_communities(P, weight="weight", seed=7)
    comms = sorted(comms, key=len, reverse=True)
    return {n: i for i, c in enumerate(comms) for n in c}


def key_players(P: nx.Graph, top_k: int = 8) -> list[dict]:
    if not P.number_of_nodes():
        return []
    bc = nx.betweenness_centrality(P, normalized=True)
    comm = communities(P)
    ranked = sorted(bc.items(), key=lambda x: (x[1], P.degree(x[0])), reverse=True)[:top_k]
    out = []
    for n, score in ranked:
        nbr_comms = {comm[m] for m in P.neighbors(n)}
        reason = (f"bridges {len(nbr_comms)} groups" if len(nbr_comms) > 1
                  else f"hub of {P.degree(n)} direct contacts")
        out.append({"id": n, "label": P.nodes[n].get("label", n), "betweenness": round(score, 4),
                    "degree": P.degree(n), "community": comm.get(n), "reason": reason,
                    "records": len(P.nodes[n].get("records") or [])})
    return out
