"""
er/translit.py — Rule-based Devanagari -> Latin transliteration.

Enough for Hindi names and addresses in FIRs: consonants carry an inherent
'a', matras replace it, virama suppresses it, and the word-final schwa is
dropped (राकेश -> raakesh, not raakesha). Zero dependencies.
Production path: IndicNER / IndicXlit (AI4Bharat), deck reference 4.
"""

from __future__ import annotations

import re

_VOWELS = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri",
           "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au"}
_MATRAS = {"ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri", "े": "e",
           "ै": "ai", "ो": "o", "ौ": "au", "ॅ": "e", "ॉ": "o"}
_CONS = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh",
         "ज": "j", "झ": "jh", "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh",
         "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n", "प": "p",
         "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l",
         "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h"}
_NUKTA_FORMS = {"क": "q", "ख": "kh", "ग": "gh", "ज": "z", "ड": "r", "ढ": "rh", "फ": "f"}
_NUKTA, _VIRAMA = "़", "्"
_NASAL = {"ं": "n", "ँ": "n", "ः": "h"}
_DIGITS = {chr(0x0966 + i): str(i) for i in range(10)}
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def has_devanagari(text: str) -> bool:
    return bool(text and _DEVANAGARI.search(text))


def transliterate(text: str) -> str:
    """Return a Latin rendering of *text*; non-Devanagari characters pass through."""
    if not has_devanagari(text):
        return text
    out: list[str] = []
    chars = list(text)
    i, n = 0, len(chars)
    while i < n:
        c = chars[i]
        if c in _CONS:
            sound = _CONS[c]
            if i + 1 < n and chars[i + 1] == _NUKTA:
                sound = _NUKTA_FORMS.get(c, sound)
                i += 1
            out.append(sound)
            nxt = chars[i + 1] if i + 1 < n else ""
            if nxt in _MATRAS:
                out.append(_MATRAS[nxt])
                i += 1
            elif nxt == _VIRAMA:
                i += 1
            elif _word_final(chars, i + 1) and not _after_conjunct(chars, i):
                pass                                   # schwa deletion at word end
            else:
                out.append("a")
        elif c in _VOWELS:
            out.append(_VOWELS[c])
        elif c in _NASAL:
            out.append(_NASAL[c])
        elif c in _DIGITS:
            out.append(_DIGITS[c])
        elif c in (_NUKTA, _VIRAMA) or c in _MATRAS:
            pass
        elif c == "।":
            out.append(".")
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _word_final(chars: list[str], j: int) -> bool:
    """True if the consonant at j-1 ends its word ('चंद' keeps its vowel: chand)."""
    if j < len(chars) and chars[j] in _NASAL:
        return False
    return j >= len(chars) or not ("ऀ" <= chars[j] <= "ॿ")


def _after_conjunct(chars: list[str], i: int) -> bool:
    """चन्द्र -> chandra: keep the final 'a' after a consonant cluster."""
    return i >= 2 and chars[i - 1] == _VIRAMA
