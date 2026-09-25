"""
extract.py — Named-entity & strong-identifier extraction from raw text.

Priority rule: regex patterns for strong identifiers (phone, IMEI, vehicle,
account) always win over NER spans. NER adds Person / Org / Location spans
for weaker evidence layered on top.

Kept under 150 lines.
"""

from __future__ import annotations
import re
from functools import lru_cache
from typing import Any

import spacy

# ── Lazy-load model so import is fast ────────────────────────────────────────

@lru_cache(maxsize=1)
def _nlp():
    try:
        return spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])
    except OSError:
        # Model not yet downloaded — caller should run:
        # python -m spacy download en_core_web_sm
        raise RuntimeError(
            "spaCy model 'en_core_web_sm' not found. "
            "Run: python -m spacy download en_core_web_sm"
        )


# ── Regex patterns ────────────────────────────────────────────────────────────

# Indian mobile: 10 digits starting with 6-9, optional +91 / 0 prefix
_RE_PHONE = re.compile(
    r"(?<!\d)(?:\+91[-\s]?|0)?([6-9]\d{9})(?!\d)"
)

# IMEI: exactly 15 consecutive digits
_RE_IMEI = re.compile(r"(?<!\d)(\d{15})(?!\d)")

# Indian vehicle registration: XX NN AA NNNN (spaces/hyphens optional)
# Examples: MH12AB1234, UP14CQ5566, DL-3C-AB-1234
_RE_VEHICLE = re.compile(
    r"\b([A-Z]{2}[-\s]?\d{1,2}[-\s]?[A-Z]{1,3}[-\s]?\d{1,4})\b",
    re.IGNORECASE,
)

# Bank account numbers: 9-18 consecutive digits NOT already captured as IMEI/phone
_RE_ACCOUNT = re.compile(r"(?<!\d)(\d{9,18})(?!\d)")

# Honourifics / relation markers to strip during NER de-noise
_NOISE = re.compile(
    r"\b(s/o|d/o|w/o|son of|daughter of|wife of|alias|a\.k\.a\.?|r/o|c/o)\b",
    re.IGNORECASE,
)


def extract_entities(text: str) -> dict[str, list[str]]:
    """Extract named entities and strong identifiers from *text*.

    Returns:
        {
            "persons":   [str, ...],   # PERSON spans from NER (de-noised)
            "phones":    [str, ...],   # 10-digit normalised numbers
            "accounts":  [str, ...],   # bank account numbers
            "vehicles":  [str, ...],   # vehicle reg numbers (upper, no spaces)
            "imeis":     [str, ...],   # 15-digit IMEIs
            "orgs":      [str, ...],   # ORG spans from NER
            "locations": [str, ...],   # GPE/LOC spans from NER
        }
    """
    # ── 1. Regex pass first ───────────────────────────────────────────────────
    phones   = _unique([m.group(1) for m in _RE_PHONE.finditer(text)])
    imeis    = _unique([m.group(1) for m in _RE_IMEI.finditer(text)])
    vehicles = _unique([
        re.sub(r"[-\s]", "", m.group(1)).upper()
        for m in _RE_VEHICLE.finditer(text)
    ])

    # Account: exclude strings already captured as IMEI or phone
    strong_digits = set(imeis) | set(phones)
    accounts = _unique([
        m.group(1) for m in _RE_ACCOUNT.finditer(text)
        if m.group(1) not in strong_digits and len(m.group(1)) != 15
    ])

    # ── 2. spaCy NER pass ─────────────────────────────────────────────────────
    doc = _nlp()(text)

    # Build a set of character ranges claimed by regex so NER can't override
    claimed: list[tuple[int, int]] = []
    for pat in [_RE_PHONE, _RE_IMEI, _RE_VEHICLE, _RE_ACCOUNT]:
        for m in pat.finditer(text):
            claimed.append((m.start(), m.end()))

    def _in_claimed(span) -> bool:
        for s, e in claimed:
            if span.start_char < e and span.end_char > s:
                return True
        return False

    persons   = []
    orgs      = []
    locations = []

    for ent in doc.ents:
        if _in_claimed(ent):
            continue
        label = ent.label_
        raw   = ent.text.strip()
        if label == "PERSON":
            cleaned = _noise_strip(raw)
            if cleaned:
                persons.append(cleaned)
        elif label == "ORG":
            orgs.append(raw)
        elif label in ("GPE", "LOC"):
            locations.append(raw)

    return {
        "persons":   _unique(persons),
        "phones":    phones,
        "accounts":  accounts,
        "vehicles":  vehicles,
        "imeis":     imeis,
        "orgs":      _unique(orgs),
        "locations": _unique(locations),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _unique(seq: list[str]) -> list[str]:
    """Deduplicate preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for x in seq:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _noise_strip(name: str) -> str:
    """Remove relational markers (s/o, d/o …) and trailing punctuation."""
    name = _NOISE.sub(" ", name)
    name = re.sub(r"\s{2,}", " ", name).strip(" ,.-")
    return name
