"""Smoke test for graphstore and analyse modules."""
import pathlib
from collections import Counter
from app.graphstore import build_graph, get_subgraph
from app.analyse import betweenness_centrality, degree_centrality, run_alert_rules

DB = str(pathlib.Path(__file__).parent.parent / "argus.db")

print("=== Building graph ===")
G = build_graph(DB)
print(f"  Nodes: {G.number_of_nodes()}  Edges: {G.number_of_edges()}")

type_counts = Counter(d.get("type", "?") for _, d in G.nodes(data=True))
for t, n in sorted(type_counts.items()):
    print(f"  {t:<15} {n}")

print()
print("=== Subgraph: P-001 (Rakesh Kumar Yadav), hops=2 ===")
sg = get_subgraph("P-001", hops=2, db_path=DB)
print(f"  Nodes: {sg.number_of_nodes()}  Edges: {sg.number_of_edges()}")
person_nodes = [(n, d["label"]) for n, d in sg.nodes(data=True) if d.get("type") == "Person"]
print(f"  Person nodes in subgraph: {person_nodes}")

# Verify Yadav cluster collapsed into master node
found = [n for n, _ in person_nodes if n == "P-001"]
ok = "PASS" if len(found) == 1 else "FAIL"
print(f"  [{ok}] Yadav cluster collapsed into single master node P-001")

print()
print("=== Betweenness centrality top-5 ===")
for item in betweenness_centrality(G, top_k=5):
    print(f"  [{item['type']:<12}] {item['label'][:35]:<35} {item['score']:.6f}")

print()
print("=== Degree centrality top-5 ===")
for item in degree_centrality(G, top_k=5):
    print(f"  [{item['type']:<12}] {item['label'][:35]:<35} {item['score']:.6f}")

print()
print("=== Running alert rules ===")
alerts = run_alert_rules(DB)
print(f"  Generated {len(alerts)} alerts")
for a in alerts:
    print(f"  [{a['rule']}]  conf={a['confidence']:.2f}")
    print(f"    {a['detail']}")
    print(f"    source_ids: {a['source_ids']}")

print()
# Verify expected alerts
serial = [a for a in alerts if a["rule"] == "SERIAL_OFFENDER_LINK"]
shared = [a for a in alerts if a["rule"] == "SHARED_DEVICE"]
print(f"  [{'PASS' if serial else 'FAIL'}] SERIAL_OFFENDER_LINK alert fired ({len(serial)} alerts)")
print(f"  [{'PASS' if shared else 'FAIL'}] SHARED_DEVICE alert fired ({len(shared)} alerts)")

yadav_alert = any("9812345678" in str(a["entities"]) for a in serial)
print(f"  [{'PASS' if yadav_alert else 'FAIL'}] Yadav phone 9812345678 in SERIAL_OFFENDER alert")
shared_phone_alert = any("9988001122" in str(a["entities"]) for a in shared)
print(f"  [{'PASS' if shared_phone_alert else 'FAIL'}] Shared phone 9988001122 in SHARED_DEVICE alert")
