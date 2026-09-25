"""
er/normalise.py — Name/address normalisation shared by blocking and scoring.

  display_name('Smt. Sunita Devi')        -> 'Sunita Devi'
  display_name('राकेश कुमार यादव')          -> 'Raakesh Kumaar Yaadav'
  phonetic('Raakesh Kumaar Yaadav')       -> 'rakesh kumar yadav'
  phonetic('Imran Qureshi')               -> 'imran kureshi'
"""

from __future__ import annotations

import re
from collections import Counter

from app.datagen.pools import LOCALITIES
from app.er.translit import transliterate

COMMON_SURNAMES = {
    "kumar", "singh", "devi", "khan", "sharma", "verma", "yadav", "gupta",
    "mishra", "pandey", "tiwari", "prasad", "lal", "ram", "kaur", "ali",
    "begum", "bano", "khatoon", "kumari", "nair", "reddy", "srivastava",
}
_HONOURIFICS = re.compile(r"\b(mr|mrs|ms|dr|shri|smt|sri|late|mohd|md)\b\.?", re.I)
_RELATIONS = re.compile(r"\b(s/o|d/o|w/o|son\s+of|daughter\s+of|wife\s+of|r/o|c/o|alias|a\.k\.a\.?|bhai)\b", re.I)
_INITIALS = re.compile(r"\b([A-Za-z])\.\s*")
_PHONETIC = [("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"), ("ai", "e"),
             ("w", "v"), ("q", "k"), ("ph", "f"), ("z", "j")]
_ADDR_STOP = {"lucknow", "nagar", "sector", "near", "road", "unknown", "approx", "gave",
              "mobile", "only", "area", "colony", "market", "house", "lane"}


def display_name(raw: str) -> str:
    """Strip honorifics/relations/punctuation, transliterate, title-case."""
    name = transliterate(raw or "")
    name = _HONOURIFICS.sub(" ", name)
    name = _RELATIONS.sub(" ", name)
    name = _INITIALS.sub(r"\1 ", name)
    name = re.sub(r"[^A-Za-z\s]", " ", name)
    return re.sub(r"\s{2,}", " ", name).strip().title()


def phonetic(raw: str) -> str:
    """Spelling-insensitive form used for similarity (Hinglish variants collapse)."""
    s = display_name(raw).lower()
    for a, b in _PHONETIC:
        s = s.replace(a, b)
    s = re.sub(r"(.)\1+", r"\1", s)                     # collapse doubled letters
    return " ".join(t[:-1] + "i" if t.endswith("y") and len(t) > 2 else t for t in s.split())


def surname(raw: str) -> str:
    toks = phonetic(raw).split()
    return toks[-1] if toks else ""


def surname_weight(name: str, corpus: Counter | None = None) -> float:
    """Common surnames carry less evidence: 'Yadav' matches say little on their own."""
    sn = surname(name)
    w = 0.55 if sn in _COMMON_PHONETIC else 1.0
    if corpus:
        freq = corpus.get(sn, 0) / max(sum(corpus.values()), 1)
        w = min(w, 0.50 if freq > 0.10 else 0.70 if freq > 0.05 else 1.0)
    return w


def surname_corpus(names: list[str]) -> Counter:
    return Counter(surname(n) for n in names if n and n.strip())


_COMMON_PHONETIC = {phonetic(c) for c in COMMON_SURNAMES}
_LOCALITY_KEYS = {phonetic(loc): loc for loc in LOCALITIES}


def localities(address: str) -> set[str]:
    """Known Lucknow localities mentioned in an address (Hindi or English)."""
    norm = phonetic(address or "")
    found = {loc for key, loc in _LOCALITY_KEYS.items() if key and key in norm}
    if not found:                                       # fall back to distinctive tokens
        found = {t for t in norm.split() if len(t) > 3 and t not in _ADDR_STOP}
    return found
