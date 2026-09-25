# Argus Frontend — Build Walkthrough

## Status: Complete ✓

All 5 tabs implemented, browser-validated with 0 JS errors.

---

## Live Recording

![Argus UI walkthrough — graph rendering and Yadav cluster](file:///C:/Users/NISARG/.gemini/antigravity-ide/brain/205b1c6c-b073-471f-ae1e-81d40b576b36/argus_graph_fix_validation_1789818833854.webp)

---

## Screenshots

````carousel
![Graph tab — Yadav cluster (25 nodes, 32 edges)](file:///C:/Users/NISARG/.gemini/antigravity-ide/brain/205b1c6c-b073-471f-ae1e-81d40b576b36/graph_rendered_after_reload_1789819035638.png)
<!-- slide -->
![Yadav cluster preset selected](file:///C:/Users/NISARG/.gemini/antigravity-ide/brain/205b1c6c-b073-471f-ae1e-81d40b576b36/yadav_cluster_final_1789819114883.png)
````

---

## Tab Summary

| Tab | Key feature | Verified |
|---|---|---|
| ① Input | "Load Demo Case" + fuzzy search | ✓ |
| ② Processing | 4-step animated checklist, live API call on step 3 | ✓ |
| ③ Graph | vis-network, colour-coded, click→side panel, presets | ✓ |
| ④ Alerts | Confidence bars, entity chips, TP/FP/TN/FN, export link | ✓ |
| ⑤ Ledger | Hash chain table, Verify (green/red), Demo Tamper | ✓ |

## Node colours
| Colour | Type |
|---|---|
| 🔵 Blue ellipse | Person |
| 🟠 Orange dot | Phone |
| 🟢 Green diamond | Account |
| 🟣 Purple box | Vehicle |
| 🩵 Teal triangle | Location |
| 🟤 Amber star | FIR |

## Design choices
- **Light theme** — white cards on #F3F4F6 background, dark text (#111827), accent #1A56DB
- **Projector-safe** — all text is dark-on-light; accent only on active states and primary buttons  
- **Inter + JetBrains Mono** — clean sans for UI, monospace for hashes
- **No build step** — vis-network loaded from `unpkg.com/vis-network@9.1.9`

## How to run
```bash
cd backend
python -X utf8 -m app.seed --reset   # fresh data if needed
uvicorn app.main:app --reload --port 8000
# open http://localhost:8000
```
