# Argus — SIH 2026 MVP (PS 26189)
Demo is tomorrow. Zero external services. No Docker, no Neo4j, no npm build.

## Stack
- Backend: Python 3.11, FastAPI, uvicorn, single SQLite file (argus.db)
- Graph: networkx, rebuilt in-memory from SQLite per request (dataset is small, this is fine)
- NLP: spaCy en_core_web_sm + regex for phone/IMEI/vehicle reg/account no
- Frontend: ONE static index.html, vis-network loaded via CDN script tag, fetch() to
  FastAPI. No React, no Vite, no npm install.
- Run: `uvicorn app.main:app --reload --port 8000`, which also serves index.html as
  static content. One terminal, one command, one URL.

## Layout
backend/app/{main.py,seed.py,ingest.py,extract.py,extract_spans.py,resolve.py,rules.py,ledger.py}
backend/app/datagen/    deterministic demo dataset + ground_truth.json (seed 26189)
backend/app/er/         transliteration, normalisation, blocking, explainable scoring, golden records
backend/app/graph/      knowledge-graph build, ego/path views, overview + key players, node details
backend/app/chain/      multi-node evidence chain (Ed25519, Merkle blocks, 3 agency nodes)
backend/app/routes/     FastAPI routers
backend/argus.db        (created at runtime, gitignored)
backend/chain_data/     chain node DBs + keys (created at runtime, gitignored)
frontend/index.html     (single file, inline <style> and <script>; exempt from the line limit)

## Checks
- `python -m app.seed --reset --fresh-chain`  clean demo state
- `python -m app.verify_resolution`            ground-truth ER acceptance test
- `python -m app._smoke_api`                   full API flow (server must be running)
- `python -m app.chain.verify`                 independent chain audit

## Domain rules — match the submitted deck exactly
- Entity types: Person, Phone, Account, Vehicle, Location, Organisation
- Strong identifiers (phone, IMEI, vehicle reg, account no) dominate match scoring;
  names are weak evidence layered on top
- Resolution gate, three-way, per slide 2's flow diagram:
  score >= 0.85 -> auto-accept, score <= 0.4 -> auto-reject, else -> human review queue
- Every Person has role: VICTIM | WITNESS | ACCUSED | UNKNOWN
  VICTIM nodes are excluded from any cross-case graph query
- Ledger: append-only SQLite table, row_hash = sha256(prev_hash + payload_json),
  /ledger/verify walks the chain and returns the first broken index or None
- The ledger lives on 3 chain nodes (backend/chain_data/<node>/node.db), never in argus.db,
  so re-ingesting case data cannot erase it. Entries are Ed25519-signed by the actor;
  blocks carry a Merkle root, a rotating proposer signature and per-node endorsements;
  a block commits only with 2 of 3 nodes validating it

## Explicitly do not
- No Docker, no Neo4j, no Kafka, nothing needing a second terminal
- No model training — TP/FP/TN/FN buttons just write a row to SQLite
- Keep every file under 150 lines; split rather than grow