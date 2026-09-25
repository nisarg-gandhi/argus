"""API smoke test — hits every endpoint and prints PASS/FAIL."""
import sys
import urllib.request
import urllib.error
import json

BASE = "http://localhost:8000"
failures = 0


def check(label: str, url: str, method: str = "GET",
          body: dict | None = None, expect: int = 200):
    global failures
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            status = r.status
            payload = json.loads(r.read())
    except urllib.error.HTTPError as e:
        status = e.code
        payload = {}
    except Exception as exc:
        print(f"  [FAIL] {label}: {exc}")
        failures += 1
        return {}

    ok = status == expect
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}  ({status})")
    if not ok:
        failures += 1
    return payload


print("=" * 60)
print("  ARGUS API SMOKE TEST")
print("=" * 60)
print()

# Health
check("GET /health", f"{BASE}/health")

# Pipeline
r = check("POST /process", f"{BASE}/process", method="POST", body={})
print(f"         extracted={r.get('extracted_firs')}  alerts={r.get('alerts_generated')}  ledger={r.get('ledger_id')}")

# Entities search
r = check("GET /entities?q=Rakesh", f"{BASE}/entities?q=Rakesh")
print(f"         results={r.get('total')}")

# Graph
r = check("GET /graph/P-001", f"{BASE}/graph/P-001")
print(f"         nodes={len(r.get('nodes',[]))}  edges={len(r.get('edges',[]))}")

# Graph – not found
check("GET /graph/NOPE (404)", f"{BASE}/graph/NOPE", expect=404)

# Review queue
r = check("GET /review-queue", f"{BASE}/review-queue")
print(f"         queue_len={r.get('count')}")

# Alerts
r = check("GET /alerts", f"{BASE}/alerts")
count = r.get("count", 0)
print(f"         count={count}")

if count:
    alert_id = r["alerts"][0]["id"]
    check(f"GET /alert/{alert_id}", f"{BASE}/alert/{alert_id}")
    check(f"POST /alert/{alert_id}/feedback (tp)",
          f"{BASE}/alert/{alert_id}/feedback",
          method="POST", body={"verdict": "tp", "actor": "demo"})
    r2 = check(f"GET /export/{alert_id}", f"{BASE}/export/{alert_id}")
    print(f"         bundle_sha256={str(r2.get('bundle_sha256',''))[:16]}...")

# Ledger
r = check("GET /ledger", f"{BASE}/ledger")
print(f"         entries={len(r.get('entries',[]))}")

r = check("GET /ledger/verify", f"{BASE}/ledger/verify")
print(f"         intact={r.get('intact')}  broken={r.get('first_broken_index')}")

# Demo tamper + re-verify
rows = r.get("entries") or []
if not rows:
    r2 = check("GET /ledger (fetch for tamper)", f"{BASE}/ledger")
    rows = r2.get("entries", [])

check("POST /demo/tamper", f"{BASE}/demo/tamper",
      method="POST", body={"row_id": 1})
r3 = check("GET /ledger/verify (after tamper)", f"{BASE}/ledger/verify")
print(f"         intact={r3.get('intact')}  broken={r3.get('first_broken_index')}")
tamper_caught = r3.get("intact") is False
print(f"  [{'PASS' if tamper_caught else 'FAIL'}] Tamper detected by verify")
if not tamper_caught:
    failures += 1

print()
print("=" * 60)
if failures == 0:
    print(f"  ALL CHECKS PASSED")
else:
    print(f"  {failures} CHECK(S) FAILED")
print("=" * 60)
sys.exit(0 if failures == 0 else 1)
