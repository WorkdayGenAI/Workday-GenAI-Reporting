"""
synonyms.py — HR / Workday domain synonym dictionary.

Terms are stored in their **stemmed** form (as produced by stemmer.stem).
Call expand_query_with_synonyms() on a list of stemmed query tokens to
inject all known synonyms.
"""

from typing import List, Set

# Each set contains stemmed forms that are considered interchangeable.
SYNONYM_GROUPS: list[set[str]] = [
    # Compensation
    {"salary", "compens", "pay", "remuner", "wage"},
    {"adjust", "chang", "modif", "revis"},

    # Workforce lifecycle
    {"termin", "separ", "exit", "departur", "offboard", "term"},
    {"hir", "recruit", "onboard"},
    {"headcount", "workforc", "staff"},
    {"transfer", "movement", "mobil", "reloc"},

    # Finance
    {"expens", "cost", "spend", "expenditur"},
    {"bonus", "incentiv", "reward"},

    # Career
    {"promot", "advanc"},

    # Performance
    {"perform", "rat", "review", "evaluat", "apprais"},

    # Personal
    {"depend", "beneficiar"},

    # People
    {"worker", "employ", "staff", "personnel"},

    # Organization
    {"organiz", "department", "team", "unit", "divis", "org"},

    # Time
    {"annual", "year"},
    {"month"},

    # Hierarchy
    {"supervisor", "manager", "leader"},

    # Growth
    {"expans", "growth"},

    # Leave / Absence
    {"leav", "absenc", "pto", "vacat", "timeoff"},

    # Benefits
    {"benefit", "coverag", "insur", "enroll", "plan"},

    # Talent / Succession
    {"talent", "success", "pipelin", "potenti"},

    # Compliance / Audit
    {"complianc", "audit", "regulat", "certif"},

    # Diversity / Inclusion
    {"divers", "dei", "inclus", "equit"},

    # Learning / Training
    {"learn", "train", "develop", "cours"},

    # Position / Job / Role
    {"posit", "job", "role", "assign"},

    # Contingent Worker
    {"conting", "contract", "temporar", "freelanc"},

    # Pre-hire
    {"prehir", "candidat", "applicant"},

    # Payroll
    {"payrol", "paycheck", "earnin"},
]

# Pre-build a lookup dict: stemmed_token → its synonym group
_LOOKUP: dict[str, Set[str]] = {}
for _group in SYNONYM_GROUPS:
    for _term in _group:
        _LOOKUP[_term] = _group


def get_synonyms(stemmed_token: str) -> Set[str]:
    """Return the synonym group for a stemmed token, or empty set."""
    return _LOOKUP.get(stemmed_token, set())


def expand_query_with_synonyms(stemmed_tokens: List[str]) -> List[str]:
    """
    Expand a list of stemmed query tokens with all known synonyms.

    Parameters
    ----------
    stemmed_tokens : list of str
        Tokens already processed by ``stemmer.tokenize()``.

    Returns
    -------
    list of str
        Original tokens plus any synonym expansions (deduplicated,
        order preserved).
    """
    expanded = list(stemmed_tokens)
    for token in stemmed_tokens:
        for syn in get_synonyms(token):
            if syn not in expanded:
                expanded.append(syn)
    return expanded
