"""
datagen/background.py — Realistic noise around the planted cases.

~95 routine FIRs (thefts, hurt, threats, burglaries...), a handful of
repeat offenders who legitimately recur across stations, everyday calls to
unregistered numbers and ordinary bank activity. Common names collide on
purpose so the resolver has to *reject* look-alikes, not just merge.
"""

from __future__ import annotations

from app.datagen import narrative as N
from app.datagen.builder import Builder
from app.datagen.pools import (COLOURS, FEMALE_SURNAMES, FIRST_F, FIRST_M,
                               LOCALITIES, SECTIONS, SURNAMES, VEHICLE_MODELS)

KINDS = ["theft"] * 5 + ["snatching"] * 3 + ["hurt"] * 4 + ["threat"] * 3 + \
        ["domestic"] * 2 + ["burglary"] * 3


def _name(b: Builder, female: bool = False) -> str:
    r = b.rng
    if female:
        return f"{r.choice(FIRST_F)} {r.choice(FEMALE_SURNAMES + SURNAMES)}"
    return f"{r.choice(FIRST_M)} {r.choice(SURNAMES)}"


def _addr(b: Builder, loc: str) -> str:
    return f"{b.rng.randint(1, 600)}, {loc}, Lucknow"


def build(b: Builder, n_firs: int = 100) -> None:
    r = b.rng
    locs = list(LOCALITIES)
    public = [b.phone() for _ in range(320)]           # unregistered numbers (shops, cabs, relatives)
    active_phones: list[tuple[str, str]] = []           # (phone, home locality)

    def accused(fid, loc, name):
        ph = b.phone() if r.random() < 0.6 else ""
        veh = ""
        if r.random() < 0.3:
            veh = b.reg()
            mk, md = r.choice(VEHICLE_MODELS)
            b.vehicle(veh, name, mk, md, r.choice(COLOURS))
        b.person(fid, name, "ACCUSED", age=r.randint(19, 55),
                 father_name=_name(b) if r.random() < 0.5 else "",
                 address=_addr(b, loc) if r.random() < 0.7 else "Unknown",
                 phone=ph, vehicle=veh)
        if ph:
            active_phones.append((ph, loc))

    for _ in range(n_firs):
        kind, loc = r.choice(KINDS), r.choice(locs)
        station, day = LOCALITIES[loc][0], r.randint(0, 110)
        female_victim = kind in ("snatching", "domestic") or r.random() < 0.3
        victim, vph = _name(b, female_victim), b.phone()
        named = r.random() < 0.55
        acc_label = _name(b) if named else ""
        text = (N.snatching(r, victim, loc) if kind == "snatching"
                else N.generic(r, kind, victim, loc, acc_label, vph if r.random() < 0.4 else ""))
        fid = b.fir(station, day, SECTIONS[kind], text)
        acct = b.account() if r.random() < 0.5 else ""
        if r.random() < 0.45:                            # RTO record for law-abiding citizens too
            mk, md = r.choice(VEHICLE_MODELS)
            b.vehicle(b.reg(), victim, mk, md, r.choice(COLOURS))
        b.person(fid, victim, "VICTIM", age=r.randint(18, 75), address=_addr(b, loc),
                 phone=vph, account_no=acct)
        active_phones.append((vph, loc))
        if acct:
            _everyday_banking(b, acct, victim, vph)
        if named:
            accused(fid, loc, acc_label)
        if r.random() < 0.35:
            wph = b.phone()
            b.person(fid, _name(b, r.random() < 0.5), "WITNESS", age=r.randint(20, 70),
                     address=_addr(b, loc), phone=wph)
            active_phones.append((wph, loc))

    _repeat_offenders(b, locs)
    _hard_cases(b, locs)
    for ph, loc in active_phones:                        # everyday calling
        for _ in range(r.randint(5, 13)):
            b.call(ph, r.choice(public), r.randint(0, 110), r.randint(7, 22),
                   r.randint(0, 59), r.randint(10, 900), loc)


def _repeat_offenders(b: Builder, locs: list[str]) -> None:
    """Small-time offenders who genuinely recur: same phone (+ same bike for some)."""
    r = b.rng
    for k in range(6):
        first, sur = r.choice(FIRST_M), r.choice(SURNAMES)
        ph, home, age = b.phone(), r.choice(locs), r.randint(22, 30)
        bike = b.reg() if k % 2 == 0 else ""
        if bike:
            b.vehicle(bike, f"{first} {sur}", "Bajaj", "Pulsar 150", "Black")
        ids = []
        for j, name in enumerate([f"{first} {sur}", f"{first[0]}. {sur}" if bike else f"{first} {sur}"]):
            loc = home if j == 0 else r.choice(locs)
            fid = b.fir(LOCALITIES[loc][0], r.randint(5, 105), SECTIONS["theft"],
                        N.generic(r, "theft", _name(b), loc, name))
            b.person(fid, _name(b), "VICTIM", age=r.randint(20, 70), address=_addr(b, loc), phone=b.phone())
            ids.append(b.person(fid, name, "ACCUSED", age=age,
                                address=f"{home}, Lucknow", phone=ph, vehicle=bike))
        b.gt["must_merge"][f"Repeat offender {first} {sur}"] = ids


def _everyday_banking(b: Builder, acct: str, holder: str, phone: str) -> None:
    r = b.rng
    b.txn(acct, holder, phone, "CREDIT", r.randint(18, 90) * 1000, r.randint(0, 10), 10, "SALARY")
    for _ in range(r.randint(2, 5)):
        b.txn(acct, holder, phone, "DEBIT", r.randint(2, 150) * 100, r.randint(0, 110), r.randint(9, 21),
              r.choice(["UPI/grocery", "UPI/fuel", "ATM WITHDRAWAL", "Electricity bill", "UPI/pharmacy"]))


def _hard_cases(b: Builder, locs: list[str]) -> None:
    """Cases the machine should NOT decide alone -> human review queue."""
    r = b.rng
    for sur in ("Chaurasia", "Bajpai"):                  # changed SIM: same man, new number
        first, father, home, age = r.choice(FIRST_M), _name(b), r.choice(locs), r.randint(25, 45)
        ids = []
        for j in range(2):
            loc = r.choice(locs)
            fid = b.fir(LOCALITIES[loc][0], r.randint(5, 105), SECTIONS["threat"],
                        N.generic(r, "threat", _name(b), loc, f"{first} {sur}"))
            b.person(fid, _name(b), "VICTIM", age=r.randint(20, 70), address=_addr(b, loc), phone=b.phone())
            ids.append(b.person(fid, f"{first} {sur}", "ACCUSED", father_name=father, age=age + j,
                                address=f"{home}, Lucknow", phone=b.phone()))
        b.gt["review"].append({"pair": ids, "truth": "same"})
    for shop in ("Sai Mobile Point", "New Janta PCO"):   # one shop phone, two unrelated customers
        loc, ph = r.choice(locs), b.phone()
        ids = []
        for j in range(2):
            fid = b.fir(LOCALITIES[loc][0], r.randint(5, 105), SECTIONS["cheating"],
                        N.generic(r, "threat", _name(b), loc, "", ph))
            ids.append(b.person(fid, _name(b), "ACCUSED", age=22 + j * 19, address=f"Near {shop}, {loc}, Lucknow",
                                phone=ph, notes=f"Gave number of {shop}"))
        b.gt["review"].append({"pair": ids, "truth": "different"})
