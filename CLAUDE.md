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
backend/app/{main.py,seed.py,extract.py,resolve.py,graphstore.py,analyse.py,ledger.py}
backend/argus.db        (created at runtime, gitignore it)
frontend/index.html     (single file, inline <style> and <script>)

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

## Explicitly do not
- No Docker, no Neo4j, no Kafka, nothing needing a second terminal
- No model training — TP/FP/TN/FN buttons just write a row to SQLite
- Keep every file under 150 lines; split rather than grow