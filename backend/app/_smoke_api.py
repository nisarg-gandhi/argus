"""API smoke test — walks the whole demo flow against a running server.

    uvicorn app.main:app --port 8000        (in one terminal)
    python -m app._smoke_api                (in another)
"""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8000"
failures = 0


def call(label: str, path: str, method: str = "GET", body: dict | None = None, expect: int = 200):
    global failures
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            status, payload = r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        status, payload = e.code, {}
    ok = status == expect
    failures += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] {label} ({status})")
    return payload


def expect(label: str, cond: bool) -> None:
    global failures
    failures += not cond
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")


print("=" * 60 + "\n  ARGUS API SMOKE TEST\n" + "=" * 60)
call("GET /health", "/health")
r = call("POST /ingest/demo", "/ingest/demo", "POST")
expect(f"5 source files hashed and sealed in block {r.get('block', {}).get('height')}", len(r.get("files", [])) == 5)
r = call("POST /process", "/process", "POST")
res = r.get("resolution", {})
print(f"         {res.get('possible_pairs')} pairs -> {res.get('candidate_pairs')} compared; "
      f"{res.get('golden_records')} golden records; {r.get('alerts', {}).get('total')} alerts")
call("GET /stats", "/stats")
call("GET /extract", "/extract")
q = call("GET /review-queue", "/review-queue")
expect("review queue has items", q.get("count", 0) > 0)
g = call("GET /resolution/golden", "/resolution/golden")
master = g["golden"][0]["master_id"] if g.get("golden") else "P-0002"
call("GET /resolution/pairs", "/resolution/pairs")
call(f"GET /graph/{master}", f"/graph/{master}")
call(f"GET /graph/{master}?resolved=false", f"/graph/{master}?resolved=false")
call("GET /graph/overview", "/graph/overview")
call("GET /graph/overview?level=entities", "/graph/overview?level=entities")
call("GET /analytics/key-players", "/analytics/key-players")
call(f"GET /node/{master}", f"/node/{master}")
call("GET /graph/NOPE (404)", "/graph/NOPE", expect=404)
if q.get("queue"):
    call("POST /review (accept)", f"/review/{q['queue'][0]['id']}", "POST", {"decision": "accept"})
a = call("GET /alerts", "/alerts")
if a.get("alerts"):
    aid = a["alerts"][0]["id"]
    call("POST feedback tp", f"/alert/{aid}/feedback", "POST", {"verdict": "tp"})
    b = call("GET /export", f"/export/{aid}")
    expect("export anchored on-chain with Merkle proof", "merkle_proof" in b.get("anchor", {}))
call("GET /feedback/stats", "/feedback/stats")
s = call("GET /chain/status", "/chain/status")
expect("all 3 nodes in consensus", s.get("consensus", {}).get("votes") == 3)
call("GET /chain/blocks", "/chain/blocks")
call("GET /chain/block/1", "/chain/block/1")
call("POST /demo/tamper (forensic_lab)", "/demo/tamper", "POST", {"node": "forensic_lab"})
s = call("GET /chain/status (after tamper)", "/chain/status")
states = {n["node"]: n["state"] for n in s.get("nodes", [])}
expect(f"tamper detected: {states}", states.get("forensic_lab") == "tampered" and s["consensus"]["quorum"])
call("POST /chain/heal/forensic_lab", "/chain/heal/forensic_lab", "POST")
s = call("GET /chain/status (after heal)", "/chain/status")
expect("consensus restored 3/3", s.get("consensus", {}).get("votes") == 3)
print("=" * 60 + f"\n  {'ALL CHECKS PASSED' if not failures else f'{failures} CHECK(S) FAILED'}\n" + "=" * 60)
sys.exit(1 if failures else 0)
