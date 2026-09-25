"""
datagen/narrative.py — FIR narrative templates (English + Hindi).

Narratives deliberately embed strong identifiers (phones, vehicle plates,
account numbers) in free text so the extraction step has real work to do.
"""

from __future__ import annotations

import random


def _amt(n: float) -> str:
    return f"Rs {n / 100000:.1f} lakh" if n >= 100000 else f"Rs {int(n):,}"


def cheating(rng: random.Random, victim: str, accused: str, phone: str,
             amount: float, vehicle: str = "", locality: str = "") -> str:
    car = f" The accused came in a car bearing registration {vehicle}." if vehicle else ""
    return rng.choice([
        f"Complainant {victim} of {locality} reported that one {accused} took "
        f"{_amt(amount)} on the promise of a government tender and absconded.{car} "
        f"The accused contacted the complainant repeatedly on mobile {phone}.",
        f"{victim} stated that {accused} posed as a contractor with contacts in the "
        f"PWD department and collected {_amt(amount)} as security money.{car} "
        f"His mobile {phone} has been switched off since the payment.",
    ])


def cyber(rng: random.Random, victim: str, account: str, phone: str,
          amount: float) -> str:
    return rng.choice([
        f"Complainant {victim} received a call from {phone} posing as bank KYC "
        f"staff and was induced to transfer {_amt(amount)} to account {account}.",
        f"{victim} reported an online job-offer fraud. After paying a registration fee "
        f"of {_amt(amount)} into account {account}, the caller on {phone} stopped responding.",
    ])


def snatching(rng: random.Random, victim: str, locality: str,
              vehicle: str = "", accused: str = "") -> str:
    who = accused or "two unknown youths"
    bike = f" on motorcycle {vehicle}" if vehicle else " on a motorcycle"
    return (f"{victim} reported that {who}{bike} snatched her mobile phone near "
            f"{locality} market and fled towards the main road.")


def ndps(rng: random.Random, accused: str, qty: int, locality: str,
         supplier: str = "", supplier_phone: str = "") -> str:
    tail = (f" During questioning he named his supplier as {supplier}, reachable on "
            f"{supplier_phone}.") if supplier else ""
    return (f"On secret information a patrol team apprehended {accused} near "
            f"{locality} and recovered {qty} grams of smack.{tail}")


def stolen_goods(rng: random.Random, accused: str, shop: str, account: str) -> str:
    return (f"Raid at {shop} recovered 14 snatched mobile phones. Proprietor {accused} "
            f"admitted paying sellers from account {account}.")


def generic(rng: random.Random, kind: str, victim: str, locality: str,
            accused: str = "", phone: str = "") -> str:
    by = f" by {accused}" if accused else " by unknown persons"
    contact = f" The complainant can be contacted on {phone}." if phone else ""
    text = {
        "theft": f"{victim} reported theft of household articles from the residence at "
                 f"{locality}{by}.",
        "hurt": f"{victim} of {locality} was assaulted{by} during a dispute over parking.",
        "threat": f"{victim} reported receiving threats{by} regarding a land dispute in "
                  f"{locality}.",
        "domestic": f"{victim} of {locality} reported cruelty and assault{by} at the "
                    f"matrimonial home.",
        "burglary": f"House of {victim} at {locality} was broken into at night{by}; "
                    f"jewellery and cash were stolen.",
    }[kind]
    return text + contact


# ── Hindi (Devanagari) narratives — multilingual ingestion demo ─────────────

def cheating_hi(victim: str, accused: str, phone: str, vehicle: str,
                amount: float) -> str:
    return (f"शिकायतकर्ता {victim} ने बताया कि {accused} ने सरकारी ठेका दिलाने के नाम "
            f"पर उनसे {int(amount):,} रुपये ले लिए। आरोपी सफेद कार {vehicle} से आया था "
            f"और मोबाइल नंबर {phone} से लगातार संपर्क करता था।")


def ndps_hi(accused: str, qty: int, phone: str) -> str:
    return (f"मुखबिर की सूचना पर पुलिस टीम ने चारबाग के पास {accused} को पकड़ा और उसके "
            f"कब्जे से {qty} ग्राम स्मैक बरामद की। आरोपी मोबाइल नंबर {phone} का प्रयोग "
            f"करता था।")
