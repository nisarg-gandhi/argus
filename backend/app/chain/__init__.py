"""
chain — Argus Evidence Chain: a permissioned, multi-node ledger.

Three agency nodes (Police HQ, Forensic Lab, Court Registry) each keep their
own SQLite copy of the chain in backend/chain_data/<node>/node.db and their
own Ed25519 key. Every entry is signed by the officer/system that created it;
every block carries a Merkle root over its entries, is signed by a rotating
proposer and endorsed (signed) by every node that validated it.

Zero external services: this mirrors Hyperledger Fabric's endorse/commit
model (deck reference 9) in-process, so the demo runs from one terminal.
"""

import pathlib

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "chain_data"
NODES = ["police_hq", "forensic_lab", "court_registry"]
NODE_LABELS = {"police_hq": "Police HQ", "forensic_lab": "State Forensic Lab",
               "court_registry": "District Court Registry"}
ACTORS = ["system", "analyst", "supervisor"]
GENESIS_HASH = "0" * 64
