"""
er/golden.py — Resolution tables, golden records (master entities) and the
review-queue housekeeping that follows every human decision.
"""

from __future__ import annotations

import json
import sqlite3

import networkx as nx

from app.er.normalise import display_name
from app.er.translit import has_devanagari

DDL = """
CREATE TABLE IF NOT EXISTS match_pairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, id_a TEXT NOT NULL, id_b TEXT NOT NULL,
    score REAL NOT NULL, decision TEXT NOT NULL, evidence_json TEXT NOT NULL,
    blocks_json TEXT NOT NULL DEFAULT '[]', ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS golden_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT, id_a TEXT NOT NULL, id_b TEXT NOT NULL,
    score REAL NOT NULL, ts TEXT NOT NULL, via TEXT NOT NULL DEFAULT 'auto');
CREATE TABLE IF NOT EXISTS review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT, id_a TEXT NOT NULL, id_b TEXT NOT NULL,
    score REAL NOT NULL, ts TEXT NOT NULL, evidence_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS human_decisions (
    id_a TEXT NOT NULL, id_b TEXT NOT NULL, decision TEXT NOT NULL,
    actor TEXT NOT NULL, ts TEXT NOT NULL, PRIMARY KEY (id_a, id_b));
CREATE TABLE IF NOT EXISTS master_entity (
    master_id TEXT PRIMARY KEY, canonical TEXT NOT NULL, role TEXT NOT NULL,
    members_json TEXT NOT NULL, names_json TEXT NOT NULL,
    identifiers_json TEXT NOT NULL, firs_json TEXT NOT NULL,
    stations_json TEXT NOT NULL, n_records INTEGER NOT NULL);
"""


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)


def clusters(conn: sqlite3.Connection) -> list[list[str]]:
    g = nx.Graph()
    g.add_edges_from((r[0], r[1]) for r in conn.execute("SELECT id_a, id_b FROM golden_entities"))
    return [sorted(c) for c in nx.connected_components(g)]


def master_map(conn: sqlite3.Connection) -> dict[str, str]:
    """person id -> master id (smallest member id) for every merged record."""
    return {pid: c[0] for c in clusters(conn) for pid in c}


def rebuild_masters(conn: sqlite3.Connection) -> int:
    """Recompute golden records from accepted pairs; prune now-redundant reviews."""
    conn.execute("DELETE FROM master_entity")
    mm: dict[str, str] = {}
    for members in clusters(conn):
        ph = ",".join("?" * len(members))
        rows = [dict(r) for r in conn.execute(
            f"SELECT p.*, f.station FROM person p JOIN fir f ON f.id = p.fir_id WHERE p.id IN ({ph})",
            members)]
        canonical = _canonical([r["name"] for r in rows])
        names = sorted({r["name"] for r in rows} | {r["alias"] for r in rows if r.get("alias")})
        ids = {f: sorted({r[f] for r in rows if r.get(f)}) for f in ("phone", "imei", "vehicle", "account_no")}
        roles = {r["role"] for r in rows}
        role = "ACCUSED" if "ACCUSED" in roles else sorted(roles)[0]
        conn.execute(
            "INSERT INTO master_entity VALUES (?,?,?,?,?,?,?,?,?)",
            (members[0], canonical, role, json.dumps(members),
             json.dumps(names, ensure_ascii=False), json.dumps(ids),
             json.dumps(sorted({r["fir_id"] for r in rows})),
             json.dumps(sorted({r["station"] for r in rows})), len(members)))
        mm.update({pid: members[0] for pid in members})
    _tidy_review(conn, mm)
    conn.commit()
    return len(set(mm.values()))


def _tidy_review(conn: sqlite3.Connection, mm: dict[str, str]) -> None:
    """One question per pair of entities: drop pairs already merged transitively,
    and keep only the strongest pair between the same two clusters."""
    best: dict[tuple[str, str], tuple[int, float]] = {}
    for rid, a, b, score in conn.execute(
            "SELECT id, id_a, id_b, score FROM review_queue ORDER BY score DESC").fetchall():
        ga, gb = mm.get(a, a), mm.get(b, b)
        if ga == gb:
            conn.execute("DELETE FROM review_queue WHERE id=?", (rid,))
            conn.execute("UPDATE match_pairs SET decision='transitive' WHERE id_a=? AND id_b=?", (a, b))
        elif tuple(sorted((ga, gb))) in best:
            conn.execute("DELETE FROM review_queue WHERE id=?", (rid,))
            conn.execute("UPDATE match_pairs SET decision='review_grouped' WHERE id_a=? AND id_b=?", (a, b))
        else:
            best[tuple(sorted((ga, gb)))] = (rid, score)


def group_pairs(conn: sqlite3.Connection, id_a: str, id_b: str) -> list[tuple[str, str]]:
    """All undecided pairs linking the entity of id_a with the entity of id_b."""
    mm = master_map(conn)
    ga, gb = mm.get(id_a, id_a), mm.get(id_b, id_b)
    return [(a, b) for a, b in conn.execute(
        "SELECT id_a, id_b FROM match_pairs WHERE decision IN ('review','review_grouped')")
        if {mm.get(a, a), mm.get(b, b)} == {ga, gb}]


def _canonical(names: list[str]) -> str:
    """Most complete Latin-script name without relation markers (s/o, alias ...)."""
    latin = [n for n in names if not has_devanagari(n)] or names
    clean = [n for n in latin if display_name(n).lower() == n.replace(".", " ").lower().strip()
             and "/" not in n] or latin
    return display_name(max(clean, key=lambda n: len(display_name(n))))
