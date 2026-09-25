"""
graph/details.py — Everything the side panel shows for one entity, pulled
straight from the source tables (so every fact is traceable to a record).
"""

from __future__ import annotations

import json
import sqlite3


def _rows(conn, sql, args=()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, args)]


def person(conn: sqlite3.Connection, pid: str) -> dict:
    m = conn.execute("SELECT * FROM master_entity WHERE master_id=? OR members_json LIKE ?",
                     (pid, f'%"{pid}"%')).fetchone()
    members = json.loads(m["members_json"]) if m else [pid]
    ph = ",".join("?" * len(members))
    records = _rows(conn, f"SELECT p.*, f.station, f.date, f.section FROM person p "
                          f"JOIN fir f ON f.id=p.fir_id WHERE p.id IN ({ph}) ORDER BY f.date", members)
    evidence = [{**r, "evidence": json.loads(r["evidence_json"])} for r in _rows(
        conn, f"SELECT id_a, id_b, score, decision, evidence_json FROM match_pairs "
              f"WHERE id_a IN ({ph}) AND id_b IN ({ph}) ORDER BY score DESC", members + members)]
    for e in evidence:
        e.pop("evidence_json")
    pending = _rows(conn, f"SELECT id, id_a, id_b, score FROM review_queue WHERE id_a IN ({ph}) OR id_b IN ({ph})",
                    members + members)
    phones = sorted({r["phone"] for r in records if r["phone"]})
    return {"kind": "Person", "golden": dict(m) if m else None, "records": records,
            "match_evidence": evidence, "pending_review": pending, "phones": phones,
            "timeline": timeline(conn, records, phones)}


def timeline(conn, records: list[dict], phones: list[str]) -> list[dict]:
    ev = [{"ts": r["date"], "kind": "FIR", "text": f"{r['fir_id']} at {r['station']} ({r['section']}) as '{r['name']}'"}
          for r in records]
    if phones:
        ph = ",".join("?" * len(phones))
        for r in conn.execute(f"SELECT substr(ts,1,7) m, COUNT(*) n, COUNT(DISTINCT callee) k FROM cdr "
                              f"WHERE caller IN ({ph}) GROUP BY m", phones):
            ev.append({"ts": r["m"] + "-28", "kind": "CDR", "text": f"{r['n']} outgoing calls to {r['k']} numbers in {r['m']}"})
    accts = sorted({r["account_no"] for r in records if r.get("account_no")})
    if accts:
        ph = ",".join("?" * len(accts))
        for r in conn.execute(f"SELECT ts, txn_type, amount, counterpart FROM bank_txn WHERE account_no IN ({ph}) "
                              f"AND amount >= 50000 ORDER BY ts", accts):
            ev.append({"ts": r["ts"][:10], "kind": "BANK",
                       "text": f"{r['txn_type']} Rs {r['amount']:,.0f} -> {r['counterpart']}"})
    return sorted(ev, key=lambda e: e["ts"])


def phone(conn, number: str) -> dict:
    stats = conn.execute("SELECT COUNT(*) n, COUNT(DISTINCT callee) k, MIN(ts) first, MAX(ts) last FROM cdr "
                         "WHERE caller=?", (number,)).fetchone()
    towers = _rows(conn, "SELECT tower_loc, COUNT(*) n FROM cdr WHERE caller=? GROUP BY tower_loc "
                         "ORDER BY n DESC LIMIT 5", (number,))
    owners = _rows(conn, "SELECT p.id, p.name, p.role, p.fir_id FROM person p WHERE p.phone=? AND p.role!='VICTIM'", (number,))
    accts = _rows(conn, "SELECT DISTINCT account_no, holder_name FROM bank_txn WHERE linked_phone=?", (number,))
    return {"kind": "Phone", "calls": dict(stats), "towers": towers, "owners": owners, "kyc_accounts": accts}


def account(conn, acct: str) -> dict:
    agg = _rows(conn, "SELECT txn_type, COUNT(*) n, SUM(amount) total FROM bank_txn WHERE account_no=? "
                      "GROUP BY txn_type", (acct,))
    incoming = _rows(conn, "SELECT account_no AS from_acct, SUM(amount) total, COUNT(*) n FROM bank_txn "
                           "WHERE counterpart=? AND txn_type='TRANSFER' GROUP BY account_no", (acct,))
    holder = conn.execute("SELECT holder_name, linked_phone FROM bank_txn WHERE account_no=? LIMIT 1", (acct,)).fetchone()
    return {"kind": "Account", "holder": dict(holder) if holder else None, "summary": agg, "incoming": incoming}


def vehicle(conn, reg: str) -> dict:
    rto = conn.execute("SELECT * FROM vehicle_reg WHERE reg_no=?", (reg,)).fetchone()
    seen = _rows(conn, "SELECT p.id, p.name, p.role, p.fir_id FROM person p WHERE p.vehicle=? AND p.role!='VICTIM'", (reg,))
    return {"kind": "Vehicle", "rto": dict(rto) if rto else None, "seen_with": seen}


def fir(conn, fid: str) -> dict:
    f = conn.execute("SELECT * FROM fir WHERE id=?", (fid,)).fetchone()
    people = _rows(conn, "SELECT id, name, role FROM person WHERE fir_id=? AND role!='VICTIM'", (fid,))
    victims = conn.execute("SELECT COUNT(*) FROM person WHERE fir_id=? AND role='VICTIM'", (fid,)).fetchone()[0]
    return {"kind": "FIR", "fir": dict(f) if f else None, "persons": people, "victims_protected": victims}


def lookup(conn: sqlite3.Connection, node_id: str) -> dict:
    prefix, _, rest = node_id.partition(":")
    if rest.startswith("V-"):
        return {"kind": "Protected", "note": "Victim identifier - withheld under DPDP Act purpose limitation"}
    handlers = {"PH": phone, "ACCT": account, "VEH": vehicle, "FIR": fir}
    if prefix in handlers and rest:
        return handlers[prefix](conn, rest)
    return person(conn, node_id)
