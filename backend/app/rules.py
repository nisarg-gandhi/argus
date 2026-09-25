"""
rules.py — Pattern detection -> explainable alerts.

  SERIAL_OFFENDER  one resolved identity named in FIRs at 2+ stations
  SHARED_DEVICE    one KYC phone controls 3+ bank accounts (mule accounts)
  CIRCULAR_FLOW    money that loops back to its origin account (layering)
  CALL_BURST       6+ outgoing calls inside 60 minutes (coordination / robocalls)
  BROKER           a person whose removal would split two criminal groups

Every alert stores human-readable evidence and the source record ids it came
from, so an analyst can contest it (the "contestable alerts" idea, ref 6).
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import networkx as nx

from app.graph.build import build_graph
from app.graph.overview import key_players, persons_graph

DDL = """CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, rule TEXT NOT NULL, title TEXT NOT NULL,
    detail TEXT NOT NULL, entities_json TEXT NOT NULL, confidence REAL NOT NULL,
    source_ids_json TEXT NOT NULL, evidence_json TEXT NOT NULL, ts TEXT NOT NULL)"""


def run_alert_rules(db_path) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(alerts)")}
        if cols and "evidence_json" not in cols:        # upgrade pre-v0.3 table
            conn.execute("DROP TABLE alerts")
        conn.execute(DDL)
        conn.execute("DELETE FROM alerts")
        G = build_graph(db_path)
        alerts = (_serial(conn) + _shared_device(conn) + _circular(G) + _bursts(conn) + _brokers(G))
        ts = datetime.now(timezone.utc).isoformat()
        for a in alerts:
            conn.execute("INSERT INTO alerts(rule,title,detail,entities_json,confidence,source_ids_json,"
                         "evidence_json,ts) VALUES (?,?,?,?,?,?,?,?)",
                         (a["rule"], a["title"], a["detail"], json.dumps(a["entities"]), round(a["confidence"], 3),
                          json.dumps(a["source_ids"]), json.dumps(a["evidence"], ensure_ascii=False), ts))
        conn.commit()
        return alerts
    finally:
        conn.close()


def _alert(rule, title, detail, entities, conf, sources, evidence) -> dict:
    return {"rule": rule, "title": title, "detail": detail, "entities": entities,
            "confidence": min(conf, 0.97), "source_ids": sources, "evidence": evidence}


def _serial(conn) -> list[dict]:
    out = []
    for m in conn.execute("SELECT * FROM master_entity WHERE role='ACCUSED'"):
        stations, firs, ids = json.loads(m["stations_json"]), json.loads(m["firs_json"]), json.loads(m["identifiers_json"])
        if len(stations) < 2:
            continue
        shared = [f"{k.replace('_no', '')} {', '.join(v)}" for k, v in ids.items() if v]
        out.append(_alert("SERIAL_OFFENDER", f"{m['canonical']} active across {len(stations)} police stations",
                          f"{m['n_records']} FIR records resolve to one person",
                          [m["master_id"]] + [f"PH:{p}" for p in ids["phone"]], 0.55 + 0.1 * len(stations), firs,
                          [f"Names used: {', '.join(json.loads(m['names_json']))}",
                           f"Stations: {', '.join(stations)}", f"Linked by: {'; '.join(shared)}"]))
    return out


def _shared_device(conn) -> list[dict]:
    out = []
    for r in conn.execute("SELECT linked_phone ph, GROUP_CONCAT(DISTINCT account_no) accts, "
                          "GROUP_CONCAT(DISTINCT holder_name) holders, COUNT(DISTINCT account_no) n "
                          "FROM bank_txn WHERE linked_phone IS NOT NULL GROUP BY linked_phone HAVING n >= 3"):
        accts = r["accts"].split(",")
        out.append(_alert("SHARED_DEVICE", f"One phone controls {r['n']} bank accounts",
                          f"KYC phone {r['ph']} is registered on accounts of different holders",
                          [f"PH:{r['ph']}"] + [f"ACCT:{a}" for a in accts], 0.55 + 0.1 * (r["n"] - 2), accts,
                          [f"Holders: {r['holders'].replace(',', ', ')}", "Classic mule-account pattern"]))
    return out


def _circular(G: nx.MultiDiGraph) -> list[dict]:
    T = nx.DiGraph()
    for u, v, d in G.edges(data=True):
        if d["etype"] == "TRANSFERRED_TO":
            T.add_edge(u, v, amount=d["amount"], first=d["first"])
    out = []
    for cyc in nx.simple_cycles(T, length_bound=5):
        if len(cyc) < 3:
            continue
        hops = list(zip(cyc, cyc[1:] + cyc[:1]))
        steps = [f"{G.nodes[a]['label']} -> {G.nodes[b]['label']}: Rs {T[a][b]['amount']:,.0f}" for a, b in hops]
        out.append(_alert("CIRCULAR_FLOW", f"Money loops through {len(cyc)} accounts back to its origin",
                          "Layering pattern: funds return to the source after passing through intermediaries",
                          cyc, 0.7 + 0.05 * len(cyc), [n.split(":", 1)[1] for n in cyc], steps))
    return out


def _bursts(conn, window=timedelta(minutes=60), min_calls=6) -> list[dict]:
    victims = {r[0] for r in conn.execute("SELECT phone FROM person WHERE role='VICTIM' AND phone IS NOT NULL")}
    calls = defaultdict(list)
    for r in conn.execute("SELECT id, caller, callee, ts FROM cdr ORDER BY ts"):
        if r["caller"] not in victims:
            calls[r["caller"]].append((datetime.fromisoformat(r["ts"]), r["callee"], r["id"]))
    out = []
    for caller, cs in calls.items():
        hot, i = [False] * len(cs), 0                    # pass 1: calls inside a dense window
        for j in range(len(cs)):
            while cs[j][0] - cs[i][0] > window:
                i += 1
            if j - i + 1 >= min_calls:
                hot[i:j + 1] = [True] * (j - i + 1)
        bursts, cur = [], []                             # pass 2: group consecutive hot calls
        for c, h in zip(cs, hot):
            if h and cur and c[0] - cur[-1][0] > window:
                bursts.append(cur)
                cur = []
            if h:
                cur.append(c)
            elif cur:
                bursts.append(cur)
                cur = []
        if cur:
            bursts.append(cur)
        if bursts:
            big = max(bursts, key=len)
            out.append(_alert("CALL_BURST", f"{len(bursts)} call burst(s) from {caller}",
                              f"{len(big)} calls to {len({c[1] for c in big})} numbers in under an hour",
                              [f"PH:{caller}"], 0.5 + 0.08 * len(bursts), [c[2] for c in big][:12],
                              [f"{b[0][0]:%d %b %H:%M}-{b[-1][0]:%H:%M}: {len(b)} calls" for b in bursts]))
    return out


def _brokers(G: nx.MultiDiGraph) -> list[dict]:
    return [_alert("BROKER", f"{k['label']} bridges separate criminal groups",
                   f"Highest betweenness in the network ({k['betweenness']:.2f}); {k['reason']}",
                   [k["id"]], 0.6 + k["betweenness"], [], [f"Betweenness centrality {k['betweenness']:.3f}",
                                                           f"{k['degree']} direct associates", k["reason"]])
            for k in key_players(persons_graph(G), 5) if k["reason"].startswith("bridges")]
