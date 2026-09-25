"""
extract_spans.py — Character-level entity spans for the FIR viewer.

Regex strong identifiers win (phone, IMEI, vehicle, account), spaCy adds
PERSON/ORG/GPE on English text, and a gazetteer of names already recorded
against the FIR catches names spaCy misses — including Devanagari names,
which the English model cannot read. Hindi narratives also get a Latin
transliteration so every analyst can read them.
"""

from __future__ import annotations

import re

from app.er.translit import has_devanagari, transliterate
from app.extract import _RE_ACCOUNT, _RE_IMEI, _RE_PHONE, _RE_VEHICLE, _nlp

_LABELS = [(_RE_PHONE, "PHONE"), (_RE_IMEI, "IMEI"), (_RE_VEHICLE, "VEHICLE"), (_RE_ACCOUNT, "ACCOUNT")]
_NER = {"PERSON": "PERSON", "ORG": "ORG", "GPE": "LOCATION", "LOC": "LOCATION", "FAC": "LOCATION"}


def _overlaps(spans: list[dict], s: int, e: int) -> bool:
    return any(s < x["end"] and e > x["start"] for x in spans)


def extract_spans(text: str, known_names: list[str] | None = None) -> dict:
    spans: list[dict] = []
    for rx, label in _LABELS:
        for m in rx.finditer(text):
            s, e = m.span(1)
            value = re.sub(r"[-\s]", "", m.group(1)).upper()
            if label == "VEHICLE" and not re.search(r"\d{3,}", value):
                continue                                  # "BNS 318" is not a number plate
            if label == "ACCOUNT" and len(value) in (10, 15):
                continue                                  # those are phones / IMEIs
            if not _overlaps(spans, s, e):
                spans.append({"start": s, "end": e, "label": label, "text": text[s:e], "source": "regex"})
    for name in sorted(set(known_names or []), key=len, reverse=True):
        for m in re.finditer(re.escape(name), text):
            if not _overlaps(spans, *m.span()):
                spans.append({"start": m.start(), "end": m.end(), "label": "PERSON",
                              "text": name, "source": "record"})
    hindi = has_devanagari(text)
    if not hindi:
        for ent in _nlp()(text).ents:
            label = _NER.get(ent.label_)
            if label and not _overlaps(spans, ent.start_char, ent.end_char):
                spans.append({"start": ent.start_char, "end": ent.end_char, "label": label,
                              "text": ent.text, "source": "spacy"})
    spans.sort(key=lambda x: x["start"])
    return {"lang": "hi" if hindi else "en", "spans": spans,
            "transliteration": transliterate(text) if hindi else None}
