# Argus — video walkthrough script

## Setup (once)
```bash
python -m venv venv && venv\Scripts\pip install -r requirements.txt
venv\Scripts\python -m spacy download en_core_web_sm
cd backend
..\venv\Scripts\python -m app.seed --reset --fresh-chain     # clean state before recording
..\venv\Scripts\python -m uvicorn app.main:app --port 8000   # open http://localhost:8000
```
Keep a second terminal open in `backend/` for the tamper shot.

## Shot list (about 6 minutes)

| # | Screen | Do | Say (deck point) |
|---|---|---|---|
| 1 | Sources | Click **Load the Lucknow demo case** | Five departments' data in one place; every file is SHA-256 fingerprinted and sealed on the chain before processing (slide 2 "Hashing"). |
| 2 | Sources | Click **Run analysis** | Walk the six stages; point at the funnel: 11,175 possible pairs, 39 compared after blocking. |
| 3 | Extraction | Open the top **हिन्दी** FIR | Multilingual: Devanagari names, plate and phone extracted; transliteration shown. |
| 4 | Resolution | Point at the gate chart | Three-way gate from slide 2: kept apart / human review / merged. Click a red dot (look-alike names kept apart). |
| 5 | Resolution | First review card: Rakesh Kumar Yadav vs Rocky Yadav (0.836) | Same handset IMEI, new SIM, just under 0.85, so the machine asks. Click **Same person, merge**; the toast shows the signed chain entry. |
| 6 | Resolution | Pintoo Singh vs Rakesh card | Shared car, different man: click **Different people**. |
| 7 | Resolution | Golden records tab, Rakesh row, **Before and after** | Five FIR records (English, initials, "s/o", alias, Hindi) collapse into one golden record. Toggle Before / After. |
| 8 | Network | Criminal network view | Three gangs found by community detection; key players ranked by betweenness (Amit Sharma and Vikas Chaurasia bridge groups). Victims are never shown. |
| 9 | Network | Path: Pintoo Singh to Salim Khan, **Find the link** | Seven hops link a car driver in a cheating case to a drug broker through the mule-account ring. |
| 10 | Network | All entities | ~400 fused entities from FIR, CDR, bank and RTO sources. |
| 11 | Alerts | Read Circular money flow and Call burst | Slide 2 patterns, each with evidence so it can be contested. Click **Confirmed (TP)**. |
| 12 | Alerts | **Export evidence** | BSA s.63(4) certificate: bundle hash, block, Merkle proof, three endorsements. Download it. |
| 13 | Evidence chain | Show the three agency nodes and blocks | Hyperledger-style endorse/commit, in-process. |
| 14 | Terminal | `python -m app.chain.tamper --node forensic_lab` | An insider edits one agency's file directly. Watch the header seal turn red within seconds. |
| 15 | Terminal | `python -m app.chain.tamper --node court_registry --rehash` then `python -m app.chain.verify` | Even recomputing every hash fails: signatures cannot be forged, and 2 of 3 agencies out-vote the copy. |
| 16 | Evidence chain | **Re-sync from the other agencies** | The repair is itself logged on-chain. |
| 17 | Terminal | `python -m app.chain.verify --evidence evidence_alert_N.json` | Anyone can prove the exported bundle is authentic, offline. |

## Planted ground truth
`backend/data/demo_case/ground_truth.json`, checked by `python -m app.verify_resolution`.
