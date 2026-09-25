"""
datagen/builder.py — Accumulates rows for every source table.

One deterministic random.Random drives all choices, so the same seed always
produces byte-identical CSVs (stable demo, stable ground truth).
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta

from app.datagen.pools import LOCALITIES, STATION_CODE

EPOCH = date(2026, 6, 1)


def day(offset: int) -> str:
    return (EPOCH + timedelta(days=offset)).isoformat()


def ts(offset: int, hour: int = 10, minute: int = 0) -> str:
    """Timestamp; minutes/hours past their range roll over (20:68 -> 21:08)."""
    t = datetime.combine(EPOCH, time()) + timedelta(days=offset, hours=hour, minutes=minute)
    return t.isoformat(timespec="seconds")


class Builder:
    def __init__(self, seed: int = 26189):
        self.rng = random.Random(seed)
        self.firs: list[dict] = []
        self.persons: list[dict] = []
        self.cdr: list[dict] = []
        self.txns: list[dict] = []
        self.vehicles: list[dict] = []
        self.gt: dict = {"must_merge": {}, "must_not_merge": [], "review": [],
                         "victims_protected": []}
        self._used: set[str] = set()

    # ── Unique identifiers ────────────────────────────────────────────────
    def _unique(self, make) -> str:
        while True:
            v = make()
            if v not in self._used:
                self._used.add(v)
                return v

    def phone(self) -> str:
        return self._unique(lambda: str(self.rng.choice("6789"))
                            + "".join(str(self.rng.randint(0, 9)) for _ in range(9)))

    def account(self) -> str:
        return self._unique(lambda: str(self.rng.randint(3, 9))
                            + "".join(str(self.rng.randint(0, 9)) for _ in range(11)))

    def imei(self) -> str:
        return self._unique(lambda: "35" + "".join(str(self.rng.randint(0, 9)) for _ in range(13)))

    def reg(self, series: str = "UP32") -> str:
        letters = "ABCDEFGHJKLMNPRSTUVWXYZ"
        return self._unique(lambda: series + self.rng.choice(letters) + self.rng.choice(letters)
                            + f"{self.rng.randint(1, 9999):04d}")

    def claim(self, *values: str) -> None:
        """Reserve hand-picked identifiers so random ones never collide."""
        self._used.update(values)

    # ── Row creators ──────────────────────────────────────────────────────
    def fir(self, station: str, offset: int, section: str, narrative: str) -> str:
        fid = f"TMP-{len(self.firs) + 1}"   # renumbered chronologically in finalise()
        self.firs.append({"id": fid, "station": station, "date": day(offset),
                          "section": section, "narrative": narrative})
        return fid

    def person(self, fir_id: str, name: str, role: str, *, alias: str = "",
               father_name: str = "", age: int | str = "", address: str = "",
               phone: str = "", vehicle: str = "", account_no: str = "",
               imei: str = "", notes: str = "") -> str:
        pid = f"P-{len(self.persons) + 1:04d}"
        self.persons.append({
            "id": pid, "fir_id": fir_id, "name": name, "alias": alias,
            "father_name": father_name, "age": age, "role": role,
            "address": address, "phone": phone, "vehicle": vehicle,
            "account_no": account_no, "imei": imei, "notes": notes,
        })
        return pid

    def call(self, a: str, b: str, offset: int, hour: int, minute: int,
             dur: int, locality: str) -> None:
        self.cdr.append({"id": "", "caller": a, "callee": b,
                         "ts": ts(offset, hour, minute), "duration_s": dur,
                         "tower_loc": LOCALITIES[locality][1]})

    def txn(self, acct: str, holder: str, phone: str, kind: str, amount: float,
            offset: int, hour: int, counterpart: str) -> None:
        self.txns.append({"id": "", "account_no": acct, "holder_name": holder,
                          "linked_phone": phone, "txn_type": kind,
                          "amount": round(float(amount), 2),
                          "ts": ts(offset, hour, self.rng.randint(0, 59)),
                          "counterpart": counterpart})

    def vehicle(self, reg: str, owner: str, make: str, model: str,
                colour: str = "") -> None:
        self.vehicles.append({
            "id": f"VEH-{len(self.vehicles) + 1:03d}", "reg_no": reg,
            "owner_name": owner, "make": make, "model": model,
            "colour": colour or self.rng.choice(["White", "Black", "Silver"]),
            "chassis_no": "MA" + "".join(self.rng.choice("0123456789ABCDEFGHJK")
                                         for _ in range(15)),
        })

    def finalise(self) -> None:
        """Sort by time and assign stable, chronological ids."""
        self.firs.sort(key=lambda f: (f["date"], f["id"]))
        seq: dict[str, int] = {}
        remap: dict[str, str] = {}
        for f in self.firs:
            code = STATION_CODE[f["station"]]
            seq[code] = seq.get(code, 0) + 1
            new_id = f"FIR-{code}-{seq[code]:03d}"
            remap[f["id"]] = new_id
            f["id"] = new_id
        for p in self.persons:
            p["fir_id"] = remap[p["fir_id"]]
        self.cdr.sort(key=lambda r: (r["ts"], r["caller"], r["callee"]))
        for i, r in enumerate(self.cdr, 1):
            r["id"] = f"CDR-{i:05d}"
        self.txns.sort(key=lambda r: (r["ts"], r["account_no"]))
        for i, r in enumerate(self.txns, 1):
            r["id"] = f"TXN-{i:04d}"
