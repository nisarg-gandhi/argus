"""
datagen/planted_fraud.py — Case A (Yadav tender-fraud gang) and
Case B (mule-account ring with circular money flow).

Both cases are wired together: gang proceeds are laundered through the
mule ring, so the graph shows two "separate" investigations are one network.
"""

from __future__ import annotations

from app.datagen import narrative as N
from app.datagen.builder import Builder
from app.datagen.planted_other import AMIT, AMIT_ACCT

YP, YP2, YIMEI = "9812345678", "9812300456", "356938035643809"
YCAR, YACCT = "UP14CQ5566", "500112233445"
SANJAY, SANJAY2, SANJAY_ACCT = "9839011122", "9839077001", "700998877665"
IMRAN, PINTU, NEHA = "9451234567", "7309876543", "8840012345"
MULE = "9988001122"
MULE_ACCTS = {"900123456789": "Mohan Lal Gupta", "900987654321": "Anjali Singh",
              "800556677889": "Farhan Qureshi", "800112299887": "Deepa Rawat"}


def build(b: Builder) -> None:
    b.claim(YP, YP2, YIMEI, YCAR, YACCT, SANJAY, SANJAY2, SANJAY_ACCT, IMRAN,
            PINTU, NEHA, MULE, *MULE_ACCTS)
    b.vehicle(YCAR, "Rakesh Kumar Yadav", "Maruti Suzuki", "Swift", "White")
    rng, gt = b.rng, b.gt
    rk, imran, sanjay, review = [], [], [], []

    def victim(fir, name, loc, day, amount, hindi_name=None):
        ph, ac = b.phone(), b.account()
        b.person(fir, hindi_name or name, "VICTIM", address=f"{loc}, Lucknow",
                 phone=ph, account_no=ac, age=rng.randint(35, 65))
        b.txn(ac, name, ph, "TRANSFER", amount, day, 12, YACCT)
        b.txn(YACCT, "Rakesh Kumar Yadav", YP, "CREDIT", amount, day, 12, ac)
        for k in range(rng.randint(4, 7)):              # grooming calls before the cheat
            b.call(NEHA if k % 2 else YP, ph, day - 3 + k // 3, 11 + k, 5, rng.randint(60, 400), "Indira Nagar")
        return ph

    cases = [  # (station, locality, day, victim, amount)
        ("PS Gomti Nagar", "Vikas Nagar", 6, "Ramesh Tiwari", 240000),
        ("PS Hazratganj", "Hazratganj", 22, "Alok Srivastava", 310000),
        ("PS Alambagh", "Alambagh", 38, "Sushil Pandey", 185000),
    ]
    for i, (st, loc, d, vname, amt) in enumerate(cases):
        f = b.fir(st, d, "BNS 318(4), 316(2)",
                  N.cheating(rng, vname, ["Rakesh Kumar Yadav", "R.K. Yadav", "Rakesh s/o Mahesh Yadav"][i], YP, amt, YCAR, loc))
        victim(f, vname, loc, d, amt)
        if i == 0:
            rk.append(b.person(f, "Rakesh Kumar Yadav", "ACCUSED", father_name="Mahesh Yadav", age=38,
                               address="Sector 12, Indira Nagar, Lucknow", phone=YP, vehicle=YCAR, imei=YIMEI))
        elif i == 1:
            rk.append(b.person(f, "R.K. Yadav", "ACCUSED", age=40, address="Indira Nagar, Lucknow (approx)",
                               phone=YP, vehicle=YCAR, notes="Vehicle noted by SHO"))
            imran.append(b.person(f, "Imran Qureshi", "ACCUSED", age=33, address="Mahanagar, Lucknow",
                                  phone=IMRAN, notes="Prepared forged tender papers"))
            b.person(f, "Neha Verma", "ACCUSED", phone=NEHA, notes="Female caller who contacted victim")
        else:
            rk.append(b.person(f, "Rakesh s/o Mahesh Yadav", "ACCUSED", alias="Rocky", father_name="Mahesh Yadav",
                               address="Unknown - gave mobile only", phone=YP, vehicle=YCAR,
                               account_no=YACCT, imei=YIMEI))
            sanjay.append(b.person(f, "Sanjay Kumar Rastogi", "ACCUSED", father_name="Ram Prakash Rastogi", age=45,
                                   address="Sector C, Aliganj, Lucknow", phone=SANJAY, account_no=SANJAY_ACCT))

    # Hindi FIR at Aminabad — same man, same phone + car, Devanagari name
    f = b.fir("PS Aminabad", 57, "BNS 318(4), 316(2)",
              N.cheating_hi("सुरेश चंद्र गुप्ता", "राकेश कुमार यादव", YP, YCAR, 275000))
    victim(f, "Suresh Chandra Gupta", "Aminabad", 57, 275000, hindi_name="सुरेश चंद्र गुप्ता")
    rk.append(b.person(f, "राकेश कुमार यादव", "ACCUSED", address="इंदिरा नगर, लखनऊ", phone=YP, vehicle=YCAR))
    imran.append(b.person(f, "इमरान कुरैशी", "ACCUSED", address="Mahanagar, Lucknow", phone=IMRAN))

    # Driver seen in the same Swift — shared vehicle, different man -> review, human rejects
    f = b.fir("PS Vikas Nagar", 70, "BNS 115(2), 351(2)", N.generic(
        rng, "threat", "Gaurav Awasthi", "Vikas Nagar", "Pintoo Singh, driver of car " + YCAR))
    b.person(f, "Gaurav Awasthi", "VICTIM", address="Vikas Nagar, Lucknow", phone=b.phone(), age=51)
    pintu = b.person(f, "Pintoo Singh", "ACCUSED", age=27, address="Chinhat, Lucknow", phone=PINTU, vehicle=YCAR)

    # New SIM, same handset IMEI — "Rocky Yadav" -> review queue (near threshold)
    f = b.fir("PS Chinhat", 84, "BNS 318(4), 316(2)",
              N.cheating(rng, "Mamta Saxena", "Rocky Yadav", YP2, 160000, "", "Chinhat"))
    b.person(f, "Mamta Saxena", "VICTIM", address="Chinhat, Lucknow", phone=b.phone(), age=44)
    rocky = b.person(f, "Rocky Yadav", "ACCUSED", age=39, address="Indira Nagar, Lucknow", phone=YP2, imei=YIMEI)

    # Sanjay again with a fresh number: same name + father + locality, no strong ID -> review
    f = b.fir("PS Mahanagar", 92, "BNS 318(4)", N.cheating(rng, "Hemant Bajpai", "Sanjay Rastogi", SANJAY2, 90000, "", "Mahanagar"))
    b.person(f, "Hemant Bajpai", "VICTIM", address="Mahanagar, Lucknow", phone=b.phone(), age=58)
    sanjay2 = b.person(f, "Sanjay Rastogi", "ACCUSED", father_name="Ram Prakash Rastogi", age=46,
                       address="Aliganj, Lucknow", phone=SANJAY2)

    # Gang communications (old SIM until day 75, new SIM after)
    for d in range(0, 110, 3):
        me = YP if d < 75 else YP2
        b.call(me, SANJAY if d < 90 else SANJAY2, d, 19, rng.randint(0, 59), rng.randint(90, 600), "Indira Nagar")
        if d % 2 == 0:
            b.call(me, PINTU, d + 1, 8, rng.randint(0, 59), rng.randint(30, 200), "Indira Nagar")
        if d % 9 == 0:
            b.call(IMRAN, me, d, 13, rng.randint(0, 59), rng.randint(60, 300), "Mahanagar")
    # Money: gang account -> Sanjay (layering) -> mule ring
    for d, amt in [(7, 150000), (23, 200000), (39, 120000), (58, 180000)]:
        b.txn(YACCT, "Rakesh Kumar Yadav", YP, "TRANSFER", amt, d + 1, 10, SANJAY_ACCT)
        b.txn(YACCT, "Rakesh Kumar Yadav", YP, "DEBIT", amt / 3, d + 2, 15, "CASH WITHDRAWAL")
        b.txn(SANJAY_ACCT, "Sanjay Kumar Rastogi", SANJAY, "TRANSFER", amt * 0.6, d + 3, 11, "900123456789")
    _mule_ring(b)

    gt["must_merge"].update({"Rakesh Kumar Yadav": rk, "Imran Qureshi": imran})
    gt["review"] += [{"pair": [rocky, rk[0]], "truth": "same"}, {"pair": [sanjay2, sanjay[0]], "truth": "same"},
                     {"pair": [pintu, rk[0]], "truth": "different"}]
    gt["must_not_merge"].append([pintu, rk[0]])


def _mule_ring(b: Builder) -> None:
    rng, accts = b.rng, list(MULE_ACCTS)
    vk = []
    for st, loc, d, name, alias in [("PS Vikas Nagar", "Vikas Nagar", 45, "Vikas Chaurasia", "Vicky"),
                                    ("PS Mahanagar", "Mahanagar", 77, "Vicky Chaurasia", "Vikas")]:
        vname, vacct, amt = f"{rng.choice(['Nidhi', 'Rohit', 'Kiran'])} {rng.choice(['Nigam', 'Shukla'])}", accts[len(vk)], 95000
        f = b.fir(st, d, "IT Act 66D, BNS 318(4)", N.cyber(rng, vname, vacct, MULE, amt))
        b.person(f, vname, "VICTIM", address=f"{loc}, Lucknow", phone=b.phone(), age=rng.randint(25, 60))
        vk.append(b.person(f, name, "ACCUSED", alias=alias, age=29, address="Vikas Nagar, Lucknow", phone=MULE))
    for k in range(6):                                  # more cyber victims paying into mule accounts
        d, amt, ac = 30 + k * 12, rng.choice([45000, 60000, 82000, 120000]), accts[k % 3]
        victim_acct = b.account()
        b.txn(victim_acct, "Online fraud victim", b.phone(), "TRANSFER", amt, d, 16, ac)
        for n in range(rng.randint(5, 8)):              # robocall-style burst before each fraud
            b.call(MULE, b.phone(), d, 10, 5 + n * 6, rng.randint(20, 90), "Vikas Nagar")
    for rnd, d in enumerate([50, 80]):                  # circular layering M -> A -> F -> M
        amt = 120000 - rnd * 20000
        cyc = [accts[0], accts[1], accts[2], accts[0]]
        for i in range(3):
            b.txn(cyc[i], MULE_ACCTS[cyc[i]], MULE, "TRANSFER", amt * (1 - 0.04 * i), d + i, 14, cyc[i + 1])
    for ac, holder in MULE_ACCTS.items():
        b.txn(ac, holder, MULE, "DEBIT", rng.randint(20, 60) * 1000, rng.randint(60, 100), 18, "CASH WITHDRAWAL")
    for d in (46, 66, 88):
        b.call(MULE, SANJAY, d, 21, 10, rng.randint(120, 400), "Vikas Nagar")
    for d, amt in ((55, 140000), (85, 90000)):          # the same mule ring also moves drug money
        b.txn(accts[2], MULE_ACCTS[accts[2]], MULE, "TRANSFER", amt, d, 23, AMIT_ACCT)
        b.call(MULE, AMIT, d - 1, 22, 40, rng.randint(60, 200), "Vikas Nagar")
    b.gt["must_merge"]["Vikas Chaurasia"] = vk
