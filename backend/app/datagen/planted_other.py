"""
datagen/planted_other.py — Case C (NDPS supply chain with a broker key player),
Case D (bike-borne phone snatchers + pawn-shop receiver),
Case E (look-alike names that must NOT merge), Case F (protected victims).
"""

from __future__ import annotations

from app.datagen import narrative as N
from app.datagen.builder import Builder

AMIT, AMIT_CAR, AMIT_ACCT = "9900112233", "UP32CY7890", "600990011223"
SALIM, SALIM_ACCT = "9335566778", "600445566778"
BHOLA, BHOLA_BIKE, BHOLA_ACCT = "9456789012", "UP32AZ1234", "600334455667"
RAJU, RAJU_ACCT, MONU = "9415098765", "300998877001", "7007654321"


def build(b: Builder) -> None:
    b.claim(AMIT, AMIT_CAR, AMIT_ACCT, SALIM, SALIM_ACCT, BHOLA, BHOLA_BIKE, BHOLA_ACCT, RAJU, RAJU_ACCT, MONU)
    _ndps(b)
    _snatchers(b)
    _lookalikes_and_victims(b)


def _ndps(b: Builder) -> None:
    rng = b.rng
    b.vehicle(AMIT_CAR, "Amit Sharma", "Honda", "Activa 6G", "Grey")
    amit, salim, peddlers = [], [], []
    spots = [("PS Alambagh", "Charbagh"), ("PS Aminabad", "Chowk"), ("PS Kaiserbagh", "Kaiserbagh"),
             ("PS Hazratganj", "Hazratganj"), ("PS Aminabad", "Aminabad"), ("PS Alambagh", "Alambagh")]
    for i, (st, loc) in enumerate(spots):
        d = 18 + i * 14
        name = f"{rng.choice(['Sonu', 'Golu', 'Chhotu', 'Pappu', 'Lucky', 'Monty'])} {rng.choice(['Rawat', 'Kashyap', 'Pal', 'Maurya'])}"
        names_supplier = i in (1, 4)
        f = b.fir(st, d, "NDPS Act 8/21/29", N.ndps(rng, name, rng.randint(12, 60), loc,
                                                    "Bunty bhai" if names_supplier else "", AMIT if names_supplier else ""))
        ph, ac = b.phone(), b.account()
        peddlers.append(ph)
        b.person(f, name, "ACCUSED", age=rng.randint(19, 28), address=f"{loc}, Lucknow", phone=ph, account_no=ac)
        if names_supplier:   # absconding supplier named by the peddler
            amit.append(b.person(f, "Bunty", "ACCUSED", phone=AMIT, vehicle=AMIT_CAR if i == 1 else "",
                                 notes="Absconding supplier, named by arrested peddler"))
        for w in range(4):   # peddlers pay the broker weekly
            b.txn(ac, name, ph, "TRANSFER", rng.randint(8, 25) * 1000, d + w * 7, 21, SALIM_ACCT)
    # Supplier arrest
    f = b.fir("PS Alambagh", 64, "NDPS Act 8/21/29", N.ndps(rng, "Amit Sharma @ Bunty", 850, "Alambagh"))
    amit.insert(0, b.person(f, "Amit Sharma", "ACCUSED", alias="Bunty", father_name="Om Prakash Sharma", age=34,
                            address="Alambagh, Lucknow", phone=AMIT, vehicle=AMIT_CAR, account_no=AMIT_ACCT))
    # Broker Salim Khan — English FIR + Hindi FIR (cross-script merge)
    f = b.fir("PS Aminabad", 71, "NDPS Act 8/21/29", N.ndps(rng, "Salim Khan", 140, "Chowk"))
    salim.append(b.person(f, "Salim Khan", "ACCUSED", father_name="Rafiq Khan", age=41,
                          address="Chowk, Lucknow", phone=SALIM, account_no=SALIM_ACCT))
    f = b.fir("PS Alambagh", 99, "NDPS Act 8/21/29", N.ndps_hi("सलीम खान", 210, SALIM))
    salim.append(b.person(f, "सलीम खान", "ACCUSED", father_name="रफ़ीक़ खान", age=41, address="Chowk, Lucknow", phone=SALIM))
    # Communications: supplier <-> broker <-> peddlers (broker is the only bridge)
    for d in range(2, 108, 4):
        b.call(AMIT, SALIM, d, 22, rng.randint(0, 59), rng.randint(60, 240), "Alambagh")
    for night in (25, 53, 81):                         # delivery-night call bursts
        for k in range(9):
            b.call(SALIM, peddlers[k % len(peddlers)], night, 20, 4 + k * 8, rng.randint(15, 60), "Chowk")
    for ph in peddlers:
        for _ in range(rng.randint(6, 10)):
            b.call(ph, SALIM, rng.randint(10, 105), rng.randint(9, 23), rng.randint(0, 59), rng.randint(20, 120), "Charbagh")
    for d in range(20, 105, 10):
        b.txn(SALIM_ACCT, "Salim Khan", SALIM, "TRANSFER", rng.randint(40, 90) * 1000, d, 11, AMIT_ACCT)
        b.txn(AMIT_ACCT, "Amit Sharma", AMIT, "CREDIT", rng.randint(1, 3) * 100000, d + 2, 20, "Hawala-coded remittance")
    b.gt["must_merge"].update({"Amit Sharma": amit, "Salim Khan": salim})


def _snatchers(b: Builder) -> None:
    rng = b.rng
    b.vehicle(BHOLA_BIKE, "Bhola Prasad", "Hero", "Splendor Plus", "Black")
    bhola = []
    for st, loc, d, name, bike in [("PS Hazratganj", "Hazratganj", 15, "Bhola Prasad", True),
                                   ("PS Kaiserbagh", "Kaiserbagh", 48, "Bholu", True),
                                   ("PS Aminabad", "Aminabad", 88, "Bhola", False)]:
        v = f"{rng.choice(['Shalini', 'Rashmi', 'Preeti'])} {rng.choice(['Saxena', 'Nigam', 'Dubey'])}"
        f = b.fir(st, d, "BNS 304", N.snatching(rng, v, loc, BHOLA_BIKE if bike else "", name if bike else ""))
        b.person(f, v, "VICTIM", address=f"{loc}, Lucknow", phone=b.phone(), age=rng.randint(20, 45))
        bhola.append(b.person(f, name, "ACCUSED", father_name="Ram Kishore" if d == 15 else "", age=24,
                              address="Charbagh, Lucknow", phone=BHOLA, vehicle=BHOLA_BIKE if bike else ""))
        if d == 48:
            b.person(f, "Monu", "ACCUSED", phone=MONU, notes="Pillion rider")
    f = b.fir("PS Aminabad", 95, "BNS 317(2)", N.stolen_goods(rng, "Raju Gupta", "Raju Electronics, Aminabad", RAJU_ACCT))
    b.person(f, "Raju Gupta", "ACCUSED", age=49, address="Aminabad, Lucknow", phone=RAJU, account_no=RAJU_ACCT)
    for d in range(16, 100, 6):
        b.call(BHOLA, RAJU, d, 17, rng.randint(0, 59), rng.randint(30, 180), "Aminabad")
        b.call(BHOLA, MONU, d + 1, 9, rng.randint(0, 59), rng.randint(30, 120), "Charbagh")
        b.txn(RAJU_ACCT, "Raju Gupta", RAJU, "TRANSFER", rng.randint(4, 12) * 1000, d + 1, 18, BHOLA_ACCT)
    b.gt["must_merge"]["Bhola Prasad"] = bhola


def _lookalikes_and_victims(b: Builder) -> None:
    rng = b.rng
    f = b.fir("PS Gomti Nagar", 30, "BNS 303(2)", N.generic(rng, "theft", "Deepak Srivastava", "Vibhuti Khand"))
    b.person(f, "Deepak Srivastava", "VICTIM", address="Vibhuti Khand, Lucknow", phone=b.phone(), age=36)
    w = b.person(f, "Sunita Devi", "WITNESS", father_name="Harish Kumar", age=34,
                 address="34 Viram Khand, Gomti Nagar, Lucknow", phone=b.phone(), notes="W/o Harish Kumar")
    f = b.fir("PS Hazratganj", 41, "BNS 74, 351(2)", N.generic(rng, "threat", "Sunita Devi", "Hazratganj"))
    b.person(f, "Sunita Devi", "VICTIM", father_name="Rampal Singh", age=22, address="Hazratganj, Lucknow", phone=b.phone())
    f = b.fir("PS Chinhat", 66, "BNS 115(2), 352", N.generic(rng, "hurt", "Kamlesh Pal", "Chinhat", "Sunita Devi"))
    b.person(f, "Kamlesh Pal", "VICTIM", address="Chinhat, Lucknow", phone=b.phone(), age=40)
    a = b.person(f, "Sunita Devi", "ACCUSED", father_name="Ramesh Pal", age=52, address="Chinhat, Lucknow", phone=b.phone())
    b.gt["must_not_merge"].append([w, a])
    # Priya Verma: victim in two FIRs, same phone — must never be linked cross-case
    priya_phone, pv = b.phone(), []
    for st, d, kind in [("PS Mahanagar", 12, "domestic"), ("PS Mahanagar", 60, "threat")]:
        f = b.fir(st, d, "BNS 85, 115(2)" if kind == "domestic" else "BNS 351(2)",
                  N.generic(rng, kind, "Priya Verma", "Mahanagar", "her husband Anand Verma", priya_phone))
        pv.append(b.person(f, "Priya Verma", "VICTIM", father_name="Anand Verma", age=29,
                           address="Mahanagar, Lucknow", phone=priya_phone))
    b.gt["victims_protected"] = pv
