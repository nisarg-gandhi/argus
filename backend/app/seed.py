# -*- coding: utf-8 -*-
"""
seed.py — Generate a realistic demo dataset into argus.db.

Usage:
    python -m app.seed            # seed only if DB is empty
    python -m app.seed --reset    # wipe argus.db and rebuild from scratch

Ground-truth plant summary (printed to stdout at end):
  GT-1  Yadav cluster  : "Rakesh Kumar Yadav" / "R.K. Yadav" / "Rakesh s/o Mahesh Yadav"
                         linked by phone 9812345678 and vehicle UP14CQ5566
                         across PS Gomtinagar, PS Hazratganj, PS Alambagh
  GT-2  Sunita split   : two unrelated people both named "Sunita Devi"
                         different phones/addresses — must NOT merge
  GT-3  Phone-accounts : phone 9988001122 appears on 3 different bank accounts
  GT-4  Victim record  : Priya Verma (role=VICTIM) — NOT connected to Yadav cluster
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import pathlib
from datetime import date, timedelta
from typing import Any

# ── DB path resolves relative to backend/ regardless of cwd ─────────────────
_HERE = pathlib.Path(__file__).resolve().parent          # backend/app/
DB_PATH = _HERE.parent / "argus.db"                      # backend/argus.db

# ── Shared identifiers that wire up ground truths ────────────────────────────
YADAV_PHONE   = "9812345678"          # GT-1 shared phone
YADAV_VEHICLE = "UP14CQ5566"          # GT-1 shared vehicle
SHARED_PHONE  = "9988001122"          # GT-3 phone linked to 3 accounts


from app.ingest import SCHEMA, wipe, create_schema, _insert

# ════════════════════════════════════════════════════════════════════════════
#  SEED DATA
# ════════════════════════════════════════════════════════════════════════════

def _d(offset: int) -> str:
    """Return ISO date string offset days from 2026-09-01."""
    return (date(2026, 9, 1) + timedelta(days=offset)).isoformat()


def _ts(offset: int, hour: int = 10, minute: int = 0) -> str:
    return f"{_d(offset)}T{hour:02d}:{minute:02d}:00"


# ── FIRs (12 across 3 stations) ──────────────────────────────────────────────

FIRS: list[dict[str, Any]] = [
    # ── PS Gomtinagar ──────────────────────────────────────────────────
    {
        "id": "FIR-GNR-001",
        "station": "PS Gomtinagar",
        "date": _d(0),
        "section": "IPC 420, 406",
        "narrative": (
            "Complainant Ramesh Tiwari reported that one Rakesh Kumar Yadav, "
            "resident of Sector 12 Indira Nagar, Lucknow, fraudulently took Rs 2.4 lakh "
            "on the pretext of getting him a government tender. The accused arrived in a "
            "white Maruti Swift bearing registration UP14CQ5566 and contacted the "
            "complainant repeatedly on mobile 9812345678. When approached for refund, "
            "the accused switched off his phone and absconded."
        ),
    },
    {
        "id": "FIR-GNR-002",
        "station": "PS Gomtinagar",
        "date": _d(3),
        "section": "IPC 379",
        "narrative": (
            "Deepak Srivastava lodged a complaint of theft of his laptop bag from "
            "Gomtinagar Viram Khand. CCTV footage shows an unknown male on a bicycle. "
            "Witness Sunita Devi (W/o Harish Kumar, 34 Viram Khand) stated she saw "
            "the man run towards the highway. Her contact number is 9001122334."
        ),
    },
    {
        "id": "FIR-GNR-003",
        "station": "PS Gomtinagar",
        "date": _d(7),
        "section": "IPC 323, 504",
        "narrative": (
            "Priya Verma, W/o Anand Verma, resident of Sarojini Nagar, reported "
            "assault and verbal abuse by her neighbour during a property dispute. "
            "Medical examination report attached. Priya can be contacted on 8877665544."
        ),
    },
    {
        "id": "FIR-GNR-004",
        "station": "PS Gomtinagar",
        "date": _d(10),
        "section": "IPC 307",
        "narrative": (
            "Ajay Pandey was stabbed near Sector-9 market. Eyewitness account from "
            "Vinod Mishra (phone 7001234567) identifies two assailants fleeing on "
            "a motorcycle. Investigation ongoing; CCTV sourcing initiated."
        ),
    },
    # ── PS Hazratganj ───────────────────────────────────────────────────
    {
        "id": "FIR-HRG-001",
        "station": "PS Hazratganj",
        "date": _d(5),
        "section": "IPC 420",
        "narrative": (
            "Mohan Lal Gupta reported that a person identifying himself as R.K. Yadav, "
            "claiming to be a senior procurement officer, defrauded him of Rs 1.8 lakh "
            "under the guise of a lucrative supply contract. The accused communicated "
            "via phone 9812345678 and was last seen driving vehicle UP14CQ5566. "
            "Similar modus operandi as case FIR-GNR-001 noted by the SHO."
        ),
    },
    {
        "id": "FIR-HRG-002",
        "station": "PS Hazratganj",
        "date": _d(8),
        "section": "IPC 354",
        "narrative": (
            "A woman, Sunita Devi, D/o Rampal Singh, of Hazratganj area (phone 9321456780), "
            "filed a complaint of molestation against an unidentified person on Mahatma "
            "Gandhi Marg. The accused fled before police arrival. Statement recorded."
        ),
    },
    {
        "id": "FIR-HRG-003",
        "station": "PS Hazratganj",
        "date": _d(12),
        "section": "IPC 468, 471",
        "narrative": (
            "Bank of Awadh branch manager reported forged cheques being presented for "
            "encashment. Account numbers 900123456789 and 900987654321 flagged. "
            "Suspect used phone 9988001122 in three separate transactions. "
            "Handwriting analysis requested."
        ),
    },
    {
        "id": "FIR-HRG-004",
        "station": "PS Hazratganj",
        "date": _d(15),
        "section": "IPC 379, 411",
        "narrative": (
            "Mobile phones and valuables worth Rs 90,000 stolen from a parked vehicle "
            "at Hazratganj market. IMEI 354521089012345 recovered from pawn shop. "
            "Accused Bhola Prasad, alias Bholu, arrested. CDR being sought from operator."
        ),
    },
    # ── PS Alambagh ─────────────────────────────────────────────────────
    {
        "id": "FIR-ALB-001",
        "station": "PS Alambagh",
        "date": _d(9),
        "section": "IPC 420, 120B",
        "narrative": (
            "Sanjay Kumar Rastogi complained that Rakesh s/o Mahesh Yadav, a.k.a. "
            "'Rocky', cheated him of Rs 3.1 lakh by claiming to arrange foreign visa "
            "processing. The fraud was perpetrated via phone 9812345678 and cash was "
            "transferred to account no 500112233445. The accused's vehicle, "
            "UP14CQ5566, was spotted parked outside the complainant's office."
        ),
    },
    {
        "id": "FIR-ALB-002",
        "station": "PS Alambagh",
        "date": _d(11),
        "section": "IPC 376",
        "narrative": (
            "Serious offence reported. Victim's name withheld per court order. "
            "Investigating officer SHO Alambagh handling. Forensic kit dispatched."
        ),
    },
    {
        "id": "FIR-ALB-003",
        "station": "PS Alambagh",
        "date": _d(14),
        "section": "IPC 147, 148, 149",
        "narrative": (
            "Unlawful assembly and rioting near Alambagh bus stand. Eight persons "
            "detained, five released on bail. Ringleader identified as Suresh alias "
            "Sonu, phone 9870011223. Property damage estimated at Rs 45,000."
        ),
    },
    {
        "id": "FIR-ALB-004",
        "station": "PS Alambagh",
        "date": _d(17),
        "section": "NDPS 20(b)(ii)(B)",
        "narrative": (
            "Patrol unit apprehended Amit Sharma with 200g charas near Alambagh "
            "railway station. Accused gave phone number 9900112233. "
            "Supplier network under investigation; CDRs of last 90 days sought."
        ),
    },
]

# ── Persons (tied to FIRs) ───────────────────────────────────────────────────

PERSONS: list[dict[str, Any]] = [
    # GT-1 Yadav cluster — three name variants, same phone + vehicle
    {
        "id": "P-001",
        "fir_id": "FIR-GNR-001",
        "name": "Rakesh Kumar Yadav",
        "role": "ACCUSED",
        "address": "Sector 12, Indira Nagar, Lucknow",
        "phone": YADAV_PHONE,
        "notes": f"Arrived in vehicle {YADAV_VEHICLE}",
    },
    {
        "id": "P-002",
        "fir_id": "FIR-HRG-001",
        "name": "R.K. Yadav",
        "role": "ACCUSED",
        "address": "Indira Nagar, Lucknow (approx)",
        "phone": YADAV_PHONE,
        "notes": f"Vehicle {YADAV_VEHICLE} noted by SHO",
    },
    {
        "id": "P-003",
        "fir_id": "FIR-ALB-001",
        "name": "Rakesh s/o Mahesh Yadav",
        "role": "ACCUSED",
        "address": "Unknown — gave mobile only",
        "phone": YADAV_PHONE,
        "notes": f"Vehicle {YADAV_VEHICLE}; alias Rocky; transferred to acct 500112233445",
    },
    # GT-2 Two unrelated Sunita Devis — must NOT merge
    {
        "id": "P-004",
        "fir_id": "FIR-GNR-002",
        "name": "Sunita Devi",
        "role": "WITNESS",
        "address": "34 Viram Khand, Gomtinagar",
        "phone": "9001122334",
        "notes": "Witness to theft; W/o Harish Kumar",
    },
    {
        "id": "P-005",
        "fir_id": "FIR-HRG-002",
        "name": "Sunita Devi",
        "role": "VICTIM",
        "address": "Hazratganj area, Lucknow",
        "phone": "9321456780",
        "notes": "D/o Rampal Singh; molestation complaint",
    },
    # GT-4 Victim Priya Verma — NOT in Yadav cluster
    {
        "id": "P-006",
        "fir_id": "FIR-GNR-003",
        "name": "Priya Verma",
        "role": "VICTIM",
        "address": "Sarojini Nagar, Lucknow",
        "phone": "8877665544",
        "notes": "Assault; W/o Anand Verma; property dispute",
    },
    # Other persons
    {
        "id": "P-007",
        "fir_id": "FIR-GNR-004",
        "name": "Ajay Pandey",
        "role": "VICTIM",
        "address": "Sector-9, Gomtinagar",
        "phone": "9123456789",
        "notes": "Stabbing victim",
    },
    {
        "id": "P-008",
        "fir_id": "FIR-GNR-004",
        "name": "Vinod Mishra",
        "role": "WITNESS",
        "address": "Sector-9 market, Lucknow",
        "phone": "7001234567",
        "notes": "Eyewitness to stabbing",
    },
    {
        "id": "P-009",
        "fir_id": "FIR-HRG-004",
        "name": "Bhola Prasad",
        "role": "ACCUSED",
        "address": "Unknown",
        "phone": "9456789012",
        "notes": "Alias Bholu; stolen phone pawn shop recovery",
    },
    {
        "id": "P-010",
        "fir_id": "FIR-ALB-003",
        "name": "Suresh",
        "role": "ACCUSED",
        "address": "Alambagh, Lucknow",
        "phone": "9870011223",
        "notes": "Alias Sonu; ringleader of unlawful assembly",
    },
    {
        "id": "P-011",
        "fir_id": "FIR-ALB-004",
        "name": "Amit Sharma",
        "role": "ACCUSED",
        "address": "Near Alambagh Railway Station",
        "phone": "9900112233",
        "notes": "NDPS arrest; supplier network under probe",
    },
    {
        "id": "P-012",
        "fir_id": "FIR-GNR-001",
        "name": "Ramesh Tiwari",
        "role": "VICTIM",
        "address": "Vikas Nagar, Lucknow",
        "phone": "9876543210",
        "notes": "Complainant; cheated of Rs 2.4 lakh",
    },
]

# ── CDR records (40) ─────────────────────────────────────────────────────────

def _cdrs() -> list[dict[str, Any]]:
    records = []
    idx = 1

    def cdr(caller, callee, offset, hour, minute, dur, tower):
        nonlocal idx
        r = {
            "id": f"CDR-{idx:04d}",
            "caller": caller,
            "callee": callee,
            "ts": _ts(offset, hour, minute),
            "duration_s": dur,
            "tower_loc": tower,
        }
        idx += 1
        return r

    # Yadav cluster calls (16 records — dense activity around fraud events)
    for day, hour, minute, callee, tower in [
        (0, 9, 15, "9876543210", "Gomtinagar Tower-3"),   # called Ramesh
        (0, 11, 30, "9876543210", "Gomtinagar Tower-3"),
        (1, 14, 0,  "9123000001", "Indira Nagar Tower-1"),
        (2, 10, 45, "9876543210", "Gomtinagar Tower-3"),
        (4, 9, 0,   "9001122334", "Hazratganj Tower-1"),  # day before HRG fraud
        (5, 10, 20, "9123000002", "Hazratganj Tower-2"),  # day of HRG fraud
        (5, 15, 0,  "9987654321", "Hazratganj Tower-2"),
        (6, 8, 30,  "9123000003", "Indira Nagar Tower-2"),
        (7, 11, 0,  "9123000004", "Alambagh Tower-1"),    # moving to Alambagh
        (8, 9, 45,  "9123000005", "Alambagh Tower-1"),
        (9, 10, 0,  "9123000006", "Alambagh Tower-2"),    # day of ALB-001
        (9, 12, 30, "9800000001", "Alambagh Tower-2"),
        (10, 8, 0,  "9123000007", "Alambagh Tower-3"),
        (11, 14, 0, "9800000002", "Unknown"),             # phone going dark
        (12, 9, 0,  "9800000003", "Unknown"),
        (15, 16, 0, "9800000004", "Kanpur Tower-1"),      # fled to Kanpur
    ]:
        records.append(cdr(YADAV_PHONE, callee, day, hour, minute, 45 + (idx % 120), tower))

    # GT-3 shared-phone calls on 3 different accounts (6 records)
    for day, callee, tower in [
        (3,  "9123456001", "Hazratganj Tower-1"),
        (6,  "9123456002", "Hazratganj Tower-2"),
        (10, "9123456003", "Alambagh Tower-1"),
        (13, "9123456004", "Alambagh Tower-2"),
        (16, "9123456005", "Hazratganj Tower-3"),
        (18, "9123456006", "Gomtinagar Tower-1"),
    ]:
        records.append(cdr(SHARED_PHONE, callee, day, 11, 0, 30 + idx, tower))

    # Bhola Prasad / stolen phone activity (4 records)
    for day, callee, tower in [
        (8,  "9456000001", "Hazratganj Tower-4"),
        (9,  "9456000002", "Alambagh Tower-2"),
        (10, "9456000003", "Alambagh Tower-2"),
        (11, "9456000004", "Gomtinagar Tower-1"),
    ]:
        records.append(cdr("9456789012", callee, day, 13, 15, 60, tower))

    # Suresh / Alambagh riot coordination (4 records)
    for day, callee, tower in [
        (13, "9870000001", "Alambagh Tower-3"),
        (13, "9870000002", "Alambagh Tower-3"),
        (14, "9870000003", "Alambagh Tower-3"),
        (14, "9870000004", "Alambagh Tower-4"),
    ]:
        records.append(cdr("9870011223", callee, day, 17, 0, 90, tower))

    # Amit Sharma (NDPS) — supplier calls (4 records)
    for day, callee, tower in [
        (10, "9900000001", "Alambagh Tower-5"),
        (12, "9900000002", "Alambagh Tower-5"),
        (15, "9900000003", "Alambagh Tower-5"),
        (17, "9900000004", "Alambagh Tower-5"),
    ]:
        records.append(cdr("9900112233", callee, day, 20, 0, 120, tower))

    # Background noise — unrelated calls (10 records)
    noise = [
        ("9876543210", "9000000001", 1, 9, 0, 35, "Gomtinagar Tower-1"),
        ("9001122334", "9000000002", 4, 14, 0, 55, "Gomtinagar Tower-2"),
        ("9321456780", "9000000003", 8, 10, 0, 40, "Hazratganj Tower-5"),
        ("8877665544", "9000000004", 7, 11, 0, 25, "Sarojini Nagar Tower-1"),
        ("7001234567", "9000000005", 10, 15, 0, 70, "Gomtinagar Tower-4"),
        ("9123456789", "9000000006", 11, 12, 0, 30, "Gomtinagar Tower-4"),
        ("9800111222", "9000000007", 6, 8, 30, 45, "Hazratganj Tower-1"),
        ("9800333444", "9000000008", 9, 17, 0, 80, "Alambagh Tower-2"),
        ("9800555666", "9000000009", 13, 10, 30, 20, "Alambagh Tower-1"),
        ("9800777888", "9000000010", 16, 14, 0, 60, "Hazratganj Tower-2"),
    ]
    for caller, callee, *rest in noise:
        records.append(cdr(caller, callee, *rest))

    return records


CDRS = _cdrs()

# ── Bank transactions (15) ───────────────────────────────────────────────────

BANK_TXNS: list[dict[str, Any]] = [
    # Yadav's target account (from ALB-001)
    {
        "id": "TXN-001",
        "account_no": "500112233445",
        "holder_name": "Rakesh Kumar Yadav",
        "linked_phone": YADAV_PHONE,
        "txn_type": "CREDIT",
        "amount": 310000.0,
        "ts": _ts(9, 16, 0),
        "counterpart": "Sanjay Kumar Rastogi",
    },
    {
        "id": "TXN-002",
        "account_no": "500112233445",
        "holder_name": "Rakesh Kumar Yadav",
        "linked_phone": YADAV_PHONE,
        "txn_type": "DEBIT",
        "amount": 200000.0,
        "ts": _ts(10, 9, 30),
        "counterpart": "CASH WITHDRAWAL",
    },
    {
        "id": "TXN-003",
        "account_no": "500112233445",
        "holder_name": "Rakesh Kumar Yadav",
        "linked_phone": YADAV_PHONE,
        "txn_type": "TRANSFER",
        "amount": 100000.0,
        "ts": _ts(10, 11, 0),
        "counterpart": "700998877665",
    },
    # GT-3 — same phone 9988001122 on 3 accounts
    {
        "id": "TXN-004",
        "account_no": "900123456789",
        "holder_name": "Mohan Lal Gupta",
        "linked_phone": SHARED_PHONE,
        "txn_type": "CREDIT",
        "amount": 180000.0,
        "ts": _ts(5, 14, 0),
        "counterpart": "NEFT INWARD",
    },
    {
        "id": "TXN-005",
        "account_no": "900987654321",
        "holder_name": "Anjali Singh",
        "linked_phone": SHARED_PHONE,
        "txn_type": "CREDIT",
        "amount": 75000.0,
        "ts": _ts(12, 11, 30),
        "counterpart": "NEFT INWARD",
    },
    {
        "id": "TXN-006",
        "account_no": "800556677889",
        "holder_name": "Farhan Qureshi",
        "linked_phone": SHARED_PHONE,
        "txn_type": "DEBIT",
        "amount": 50000.0,
        "ts": _ts(14, 15, 0),
        "counterpart": "UPI/9988001122@ybl",
    },
    # Forged cheque account from HRG-003
    {
        "id": "TXN-007",
        "account_no": "900123456789",
        "holder_name": "Mohan Lal Gupta",
        "linked_phone": SHARED_PHONE,
        "txn_type": "DEBIT",
        "amount": 45000.0,
        "ts": _ts(12, 10, 0),
        "counterpart": "FORGED CHEQUE #4512",
    },
    # Bhola Prasad — pawn money
    {
        "id": "TXN-008",
        "account_no": "600334455667",
        "holder_name": "Bhola Prasad",
        "linked_phone": "9456789012",
        "txn_type": "CREDIT",
        "amount": 8500.0,
        "ts": _ts(9, 17, 0),
        "counterpart": "Raju Electronics Pawn",
    },
    # Suresh — riot-related cash
    {
        "id": "TXN-009",
        "account_no": "600778899001",
        "holder_name": "Suresh Verma",
        "linked_phone": "9870011223",
        "txn_type": "CREDIT",
        "amount": 25000.0,
        "ts": _ts(13, 8, 0),
        "counterpart": "UNKNOWN CASH DEPOSIT",
    },
    # Amit Sharma — NDPS supplier payment
    {
        "id": "TXN-010",
        "account_no": "600990011223",
        "holder_name": "Amit Sharma",
        "linked_phone": "9900112233",
        "txn_type": "CREDIT",
        "amount": 60000.0,
        "ts": _ts(16, 20, 30),
        "counterpart": "Hawala-coded remittance",
    },
    # Victim Priya Verma — completely unrelated transactions
    {
        "id": "TXN-011",
        "account_no": "400223344556",
        "holder_name": "Priya Verma",
        "linked_phone": "8877665544",
        "txn_type": "DEBIT",
        "amount": 12000.0,
        "ts": _ts(6, 10, 0),
        "counterpart": "City Hospital Medical Bill",
    },
    # Background noise
    {
        "id": "TXN-012",
        "account_no": "300112233001",
        "holder_name": "Ramesh Tiwari",
        "linked_phone": "9876543210",
        "txn_type": "DEBIT",
        "amount": 240000.0,
        "ts": _ts(0, 13, 0),
        "counterpart": "Rakesh Kumar Yadav",
    },
    {
        "id": "TXN-013",
        "account_no": "300445566002",
        "holder_name": "Deepak Srivastava",
        "linked_phone": "9800991122",
        "txn_type": "DEBIT",
        "amount": 55000.0,
        "ts": _ts(3, 9, 30),
        "counterpart": "LAPTOP PURCHASE",
    },
    {
        "id": "TXN-014",
        "account_no": "300778899003",
        "holder_name": "Ajay Pandey",
        "linked_phone": "9123456789",
        "txn_type": "DEBIT",
        "amount": 8000.0,
        "ts": _ts(10, 14, 0),
        "counterpart": "Medical Emergency",
    },
    {
        "id": "TXN-015",
        "account_no": "300901122004",
        "holder_name": "Vinod Mishra",
        "linked_phone": "7001234567",
        "txn_type": "CREDIT",
        "amount": 15000.0,
        "ts": _ts(11, 11, 0),
        "counterpart": "SALARY",
    },
]

# ── Vehicle registrations (8) ─────────────────────────────────────────────────

VEHICLES: list[dict[str, Any]] = [
    # GT-1 Yadav's vehicle — shared across 3 FIRs
    {
        "id": "VEH-001",
        "reg_no": YADAV_VEHICLE,
        "owner_name": "Rakesh Kumar Yadav",
        "make": "Maruti Suzuki",
        "model": "Swift",
        "colour": "White",
        "chassis_no": "MA3EYD81S00123456",
    },
    # Bhola Prasad's motorcycle (mentioned in FIR-GNR-004 as noise)
    {
        "id": "VEH-002",
        "reg_no": "UP32AZ1234",
        "owner_name": "Bhola Prasad",
        "make": "Hero",
        "model": "Splendor Plus",
        "colour": "Black",
        "chassis_no": "MBLHA10A3CHG12345",
    },
    # Suresh's vehicle — riot
    {
        "id": "VEH-003",
        "reg_no": "UP32BX4567",
        "owner_name": "Suresh Verma",
        "make": "Bajaj",
        "model": "Pulsar 150",
        "colour": "Blue",
        "chassis_no": "MD2A11BZ5HCG67890",
    },
    # Amit Sharma's vehicle — NDPS
    {
        "id": "VEH-004",
        "reg_no": "UP32CY7890",
        "owner_name": "Amit Sharma",
        "make": "Honda",
        "model": "Activa 6G",
        "colour": "Grey",
        "chassis_no": "ME4JC651NN8012345",
    },
    # Ramesh Tiwari (victim/complainant)
    {
        "id": "VEH-005",
        "reg_no": "UP32DZ0011",
        "owner_name": "Ramesh Tiwari",
        "make": "Toyota",
        "model": "Innova Crysta",
        "colour": "Silver",
        "chassis_no": "MHFYX59G9K2012345",
    },
    # Background / unrelated
    {
        "id": "VEH-006",
        "reg_no": "UP32EA1122",
        "owner_name": "Deepak Srivastava",
        "make": "Hyundai",
        "model": "i20",
        "colour": "Red",
        "chassis_no": "MALAN51CLGM012345",
    },
    {
        "id": "VEH-007",
        "reg_no": "UP32FB2233",
        "owner_name": "Mohan Lal Gupta",
        "make": "Tata",
        "model": "Nexon",
        "colour": "Teal",
        "chassis_no": "MAT610634K1012345",
    },
    {
        "id": "VEH-008",
        "reg_no": "UP32GC3344",
        "owner_name": "Vinod Mishra",
        "make": "Maruti Suzuki",
        "model": "Wagon R",
        "colour": "White",
        "chassis_no": "MA3EWDE1S00234567",
    },
]


# ════════════════════════════════════════════════════════════════════════════
#  DB HELPERS & CSV EXPORT
# ════════════════════════════════════════════════════════════════════════════

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def export_to_csv(data: list[dict], out_path: pathlib.Path) -> None:
    if not data:
        return
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)


def seed(conn: sqlite3.Connection) -> None:
    # 1. Insert into DB (for backward compatibility / tests)
    _insert(conn, "fir", FIRS)
    _insert(conn, "person", PERSONS)
    _insert(conn, "cdr", CDRS)
    _insert(conn, "bank_txn", BANK_TXNS)
    _insert(conn, "vehicle_reg", VEHICLES)
    conn.commit()

    # 2. Export to CSV for the upload flow demo
    import csv
    out_dir = _HERE.parent / "data" / "demo_case"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    export_to_csv(FIRS, out_dir / "fir.csv")
    export_to_csv(PERSONS, out_dir / "person.csv")
    export_to_csv(CDRS, out_dir / "cdr.csv")
    export_to_csv(BANK_TXNS, out_dir / "bank_txn.csv")
    export_to_csv(VEHICLES, out_dir / "vehicle_reg.csv")
    
    print(f"[*] Exported demo datasets to {out_dir}")


# ════════════════════════════════════════════════════════════════════════════
#  GROUND-TRUTH REPORT
# ════════════════════════════════════════════════════════════════════════════

def print_ground_truths() -> None:
    sep = "=" * 70

    print("\n" + sep)
    print("  ARGUS -- SEED GROUND-TRUTH VERIFICATION REPORT")
    print(sep)

    print("\n+-- GT-1  YADAV CLUSTER (must link across 3 FIRs / 3 stations) ------")
    print("|  Name variants:")
    for p in PERSONS:
        if p["phone"] == YADAV_PHONE and p["role"] == "ACCUSED":
            print(f"|    [{p['id']}]  \"{p['name']}\"  (FIR: {p['fir_id']}, Station: {next(f['station'] for f in FIRS if f['id']==p['fir_id'])})")
    print(f"|  Shared phone  : {YADAV_PHONE}")
    print(f"|  Shared vehicle: {YADAV_VEHICLE}")
    yadav_firs = [p["fir_id"] for p in PERSONS if p["phone"] == YADAV_PHONE and p["role"] == "ACCUSED"]
    yadav_stations = [f["station"] for f in FIRS if f["id"] in yadav_firs]
    print(f"|  FIRs          : {', '.join(yadav_firs)}")
    print(f"|  Stations      : {', '.join(yadav_stations)}")
    print("+" + "-" * 69)

    print("\n+-- GT-2  SUNITA DEVI SPLIT (must NOT merge) --------------------------")
    for p in PERSONS:
        if p["name"] == "Sunita Devi":
            station = next(f["station"] for f in FIRS if f["id"] == p["fir_id"])
            print(f"|    [{p['id']}]  role={p['role']}  phone={p['phone']}")
            print(f"|              address=\"{p['address']}\"  FIR={p['fir_id']} ({station})")
    print("|  -> Different phone, different address, different FIR -- NO merge")
    print("+" + "-" * 69)

    print("\n+-- GT-3  SHARED PHONE ON 3 ACCOUNTS ----------------------------------")
    print(f"|  Phone: {SHARED_PHONE}")
    for t in BANK_TXNS:
        if t["linked_phone"] == SHARED_PHONE:
            print(f"|    [{t['id']}]  acct={t['account_no']}  holder=\"{t['holder_name']}\"")
    print("+" + "-" * 69)

    print("\n+-- GT-4  VICTIM RECORD (Priya Verma -- NOT in Yadav cluster) ---------")
    for p in PERSONS:
        if p["id"] == "P-006":
            station = next(f["station"] for f in FIRS if f["id"] == p["fir_id"])
            print(f"|    [{p['id']}]  name=\"{p['name']}\"  role={p['role']}")
            print(f"|              phone={p['phone']}  FIR={p['fir_id']} ({station})")
    print("|  -> role=VICTIM; excluded from cross-case graph queries")
    print("+" + "-" * 69)

    print("\n+-- DATASET SUMMARY ----------------------------------------------------")
    print(f"|  FIRs         : {len(FIRS):3d}  (across {len({f['station'] for f in FIRS})} stations)")
    print(f"|  Persons      : {len(PERSONS):3d}")
    print(f"|  CDR records  : {len(CDRS):3d}")
    print(f"|  Bank txns    : {len(BANK_TXNS):3d}")
    print(f"|  Vehicles     : {len(VEHICLES):3d}")
    print(f"|  DB path      : {DB_PATH}")
    print("+" + "-" * 69)
    print()


# ════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed argus.db with demo data")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe existing tables and rebuild from scratch (safe mid-demo recovery)",
    )
    args = parser.parse_args()

    conn = _connect()
    try:
        if args.reset:
            print("[seed] --reset: dropping existing tables ...")
            wipe(conn)

        print("[seed] creating schema ...")
        create_schema(conn)

        # Check if already seeded (skip on partial / allow reset path)
        row = conn.execute("SELECT COUNT(*) FROM fir").fetchone()
        if row[0] > 0 and not args.reset:
            print(f"[seed] DB already contains {row[0]} FIR rows — skipping insert. Use --reset to rebuild.")
        else:
            print("[seed] inserting seed data ...")
            seed(conn)
            print("[seed] DONE.")

        print_ground_truths()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
