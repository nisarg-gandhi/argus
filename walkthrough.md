# Argus — screen-recording script (~8 min)

## Before you hit record
1. Server terminal (in `backend/`): Ctrl+C, then
   `..\venv\Scripts\python -m app.seed --reset --fresh-chain`
   `..\venv\Scripts\python -m uvicorn app.main:app --port 8000`
2. Open a second terminal in the same `backend/` folder (off-screen).
3. Chrome: `http://localhost:8000`, Ctrl+F5, F11, zoom 100%.
4. Check the seal (top right) says "3 of 3 agencies agree". Start recording.

## Part 1 — Sources
1. Point at the seal. *"Argus brings FIRs, call records, bank transactions and vehicle registrations from different departments into one workbench. That seal is our evidence chain."*
2. Click **Load the Lucknow demo case**. *"147 FIRs across 8 stations. Each file is fingerprinted with SHA-256 and sealed on the chain before anything reads it."*
3. Point at "Fingerprints sealed in block 1", click **Run analysis**, wait ~5 s. *"One click runs extraction, resolution, network building and pattern detection."*
4. Point at the stage-3 funnel. *"11,175 possible pairs, blocking cuts it to 39: 21 merged, 7 for a human, 7 kept apart. Victims are never compared."*

## Part 2 — Extraction
5. Click **2 Extraction** (Hindi FIR opens). *"Names, plate and phone pulled straight out of Devanagari text, with a transliteration."*
6. Click an English FIR. *"Exact patterns for identifiers, spaCy NER for names, places and organisations."*

## Part 3 — Entity resolution
7. Click **3 Entity resolution**, point at the chart. *"The three-way gate: below 0.40 apart, above 0.85 merged, in between a human decides."*
8. **Every scored pair** tab → bottom → click the **Sunita Devi / Sunita Devi** row. *"Same name, different husband, 18-year age gap: evidence against, kept apart."*
9. **Needs your decision** tab, first card (Rakesh Kumar Yadav vs Rocky Yadav). *"0.836, just under the line: same IMEI, new SIM, common surname. The machine explains and asks."*
10. Click **Same person, merge**, point at the toast. *"Signed with my key, sealed on the chain, replayed on every future run."*
11. Scroll to the **Pintoo Singh** card, click **Different people**. *"Same car, different man."*
12. **Golden records** tab, point at Rakesh. *"Five FIRs, five spellings including Hindi: one golden record across 5 stations."*
13. Click **Before and after**. *"Before resolution, five separate people…"*
14. Click **After resolution**. *"…after, one person and his whole network."*

## Part 4 — Network
15. Click **Criminal network**. *"Suspects linked by calls, money, shared identifiers or joint FIRs; colours show the evidence kind. Victims never shown."*
16. In **Groups found**, click **Rakesh Kumar Yadav and 7 others**. *"Community detection finds the gangs automatically."*
17. Click it again to clear; point at **Key players** (Amit Sharma, Vikas Chaurasia); click a person node. *"Betweenness finds the brokers bridging groups. Clicking isolates direct links."*
18. **Connect two people**: `Pintoo Singh` → `Salim Khan` → **Find the link**. *"A driver in a cheating case, 7 hops from a drug broker, through the mule-account ring."*
19. Click **All entities**, click the **FIR** legend chip, search `Salim Khan`. *"~400 fused entities from four sources, filterable and searchable."*

## Part 5 — Alerts and export
20. Click **5 Alerts**, scroll past Serial offender, Circular money flow, Call burst. *"Patterns found automatically, each with its evidence so it can be contested."*
21. First alert → **Confirmed (TP)**. *"Officer feedback is signed onto the chain and tracked per rule."*
22. **Export evidence** → point at hash, block, Merkle proof → **Download bundle** → **Close**. *"BSA Section 63(4) certificate, anchored on the chain, endorsed by three agencies."*

## Part 6 — Evidence chain and tampering
23. Click **6 Evidence chain**; point at the three agencies, the block strip, click the last block (Merkle tree). *"Each agency keeps its own copy; entries signed by officers, blocks Merkle-sealed and endorsed."*
24. Terminal 2: `..\venv\Scripts\python -m app.chain.tamper --node forensic_lab`. *"An insider edits the Forensic Lab's database file directly."*
25. Browser: wait ~4 s for the red seal; point at the error. *"Caught instantly; the other two agencies still agree."*
26. Click **Re-sync from the other agencies**. *"Restored, and the repair itself is logged on the chain."*
27. Terminal: `..\venv\Scripts\python -m app.chain.tamper --node court_registry --rehash`. *"A smarter attacker recomputes every hash."*
28. Terminal: `..\venv\Scripts\python -m app.chain.verify`. *"Hashes line up, but signatures can't be forged; two agencies out-vote it."*
29. Browser: **Re-sync** the Court Registry card (seal goes green).
30. Terminal: `..\venv\Scripts\python -m app.chain.verify --evidence C:\Users\divys\Downloads\evidence_alert_<N>.json` *"Anyone, even a court, can prove the evidence is unaltered without our server."*

## Close
31. Back to **4 Network**. *"Every source in one place, identities resolved with explanations, hidden networks revealed, and tamper-evident, court-ready evidence. Fully offline on one machine."*

**If a take goes wrong:** Ctrl+C the server, rerun the reset command, restart, Ctrl+F5.

Ground truth for the planted cases: `backend/data/demo_case/ground_truth.json` (`python -m app.verify_resolution`).
