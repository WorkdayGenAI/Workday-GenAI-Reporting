"""
stemmer.py — Lightweight suffix-stripping stemmer for English text.

Designed for the Report Ranking Agent. Not a full Porter/Snowball stemmer,
but validated to handle Workday/HR domain vocabulary effectively.
"""

import re
from typing import List

# Suffixes ordered longest → shortest to prevent over-stripping.
_SUFFIXES = [
    "ations", "ation", "tions", "ments", "iness",
    "ness", "ment", "tion", "able", "ible",
    "ally", "ful", "ous", "ive",
    "ing", "ies", "ily",
    "ed", "ly", "er",
    "es", "s",
]

_MIN_STEM_LENGTH = 3  # Never strip a word below this length.


def stem(word: str) -> str:
    """
    Strip one suffix from *word* and return the stem.

    Examples
    --------
    >>> stem("terminations")
    'termin'
    >>> stem("expenses")
    'expens'
    >>> stem("compensation")
    'compens'
    >>> stem("the")
    'the'
    """
    w = word.lower().strip()
    if len(w) <= _MIN_STEM_LENGTH:
        return w
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= _MIN_STEM_LENGTH:
            return w[: -len(suf)]
    return w


def tokenize(text: str) -> List[str]:
    """Lowercase, handle hyphens, remove non-alphanumeric chars, split, and stem.
    
    Hyphenated words (e.g. 'Pre-Hire') produce both the joined form ('prehir')
    and the individual parts ('pre', 'hir') so queries work either way.
    """
    text_lower = text.lower()
    
    # First, find hyphenated compounds and generate joined variants
    hyphenated = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)+", text_lower)
    joined_tokens = []
    for compound in hyphenated:
        # Add the joined form (e.g. "pre-hire" → "prehire")
        joined = compound.replace("-", "")
        joined_tokens.append(stem(joined))
    
    # Standard tokenization: strip non-alphanumeric, split, stem
    plain = re.sub(r"[^a-z0-9\s]", " ", text_lower).split()
    tokens = [stem(w) for w in plain if w]
    
    # Merge: add joined tokens that aren't already present
    for jt in joined_tokens:
        if jt not in tokens:
            tokens.append(jt)
    
    return tokens


def tokenize_plain(text: str) -> List[str]:
    """Lowercase, remove non-alphanumeric chars, split (no stemming)."""
    return re.sub(r"[^a-z0-9\s]", "", text.lower()).split()
