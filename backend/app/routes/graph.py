"""
routes/graph.py — GET /graph/{master_id}
Returns the ego-subgraph as a vis-network compatible node/edge list.
"""

from __future__ import annotations

import pathlib

from fastapi import APIRouter, HTTPException, Query

from app.graphstore import get_subgraph

router = APIRouter(tags=["graph"])

_DB = pathlib.Path(__file__).resolve().parent.parent.parent / "argus.db"

# Colour palette per node type (vis-network)
_COLOURS: dict[str, dict] = {
    "Person":       {"background": "#DBEAFE", "border": "#93C5FD"},
    "Phone":        {"background": "#FFEDD5", "border": "#FDBA74"},
    "Account":      {"background": "#DCFCE7", "border": "#86EFAC"},
    "Vehicle":      {"background": "#F3E8FF", "border": "#D8B4FE"},
    "Location":     {"background": "#CCFBF1", "border": "#5EEAD4"},
    "Organisation": {"background": "#FEE2E2", "border": "#FCA5A5"},
    "FIR":          {"background": "#FEF9C3", "border": "#FDE047"},
}

# Edge colour per etype
_EDGE_COLOURS: dict[str, str] = {
    "OWNS":          "#95A5A6",
    "CALLED":        "#F39C12",
    "TRANSFERRED_TO":"#27AE60",
    "REGISTERED_TO": "#8E44AD",
    "NAMED_IN":      "#2980B9",
    "SAME_AS":       "#E74C3C",
}


@router.get("/graph/{master_id}")
def get_graph(
    master_id: str,
    hops: int = Query(default=2, ge=1, le=4, description="Hop depth"),
):
    """Return vis-network node/edge payload for *master_id* ego-graph.

    master_id is a graph node ID, e.g. 'P-001', 'PH:9812345678'.
    """
    sg = get_subgraph(master_id, hops=hops, db_path=_DB)

    if sg.number_of_nodes() == 0:
        raise HTTPException(status_code=404, detail=f"Node '{master_id}' not found in graph")

    nodes = []
    for nid, data in sg.nodes(data=True):
        ntype  = data.get("type", "?")
        colour = _COLOURS.get(ntype, {"background": "#F3F4F6", "border": "#D1D5DB"})
        node_obj = {
            "id":    nid,
            "label": data.get("label", nid),
            "group": ntype,
            "color": colour,
            "title": _node_tooltip(nid, data),
        }
        if data.get("dashed"):
            node_obj["shapeProperties"] = {"borderDashes": True}
        if "children" in data:
            node_obj["children"] = data["children"]
        if data.get("alert"):
            node_obj["alert"] = True
        nodes.append(node_obj)

    edges = []
    edge_id = 0
    for src, dst, data in sg.edges(data=True):
        etype = data.get("etype", "LINK")
        edges.append({
            "id":     edge_id,
            "from":   src,
            "to":     dst,
            "label":  etype,
            "color":  {"color": _EDGE_COLOURS.get(etype, "#BDC3C7")},
            "arrows": "to",
            "title":  _edge_tooltip(data),
        })
        edge_id += 1

    return {
        "master_id": master_id,
        "hops": hops,
        "nodes": nodes,
        "edges": edges,
    }


def _node_tooltip(nid: str, data: dict) -> str:
    parts = [f"<b>{data.get('label', nid)}</b>", f"Type: {data.get('type','?')}"]
    if data.get("review_badge"):
        parts.append(f"<span style='color:#E74C3C;font-weight:bold'>[{data['review_badge']}]</span>")
    for k in ("role", "station", "make", "model", "holder"):
        if k in data and data[k]:
            parts.append(f"{k.title()}: {data[k]}")
    if data.get("aka"):
        parts.append(f"Aka: {', '.join(data['aka'])}")
    return "<br>".join(parts)


def _edge_tooltip(data: dict) -> str:
    parts = [f"<b>{data.get('etype','LINK')}</b>"]
    for k in ("ts", "dur", "amount", "tower", "score"):
        if k in data and data[k] is not None:
            parts.append(f"{k}: {data[k]}")
    return "<br>".join(parts)
