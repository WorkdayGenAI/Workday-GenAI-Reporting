"""
bm25_engine.py — BM25Okapi search engine built from scratch.

Provides two classes:
- ``BM25``: the core ranking algorithm.
- ``ReportIndex``: wraps BM25 with report-specific composite text
  construction, tokenisation, and a convenient ``search()`` method.
"""

import math
from collections import Counter
from typing import Any, Dict, List, Tuple

import config
from stemmer import tokenize as stem_tokenize
from synonyms import expand_query_with_synonyms


# ─────────────────────────────────────────────
# BM25 core
# ─────────────────────────────────────────────
class BM25:
    """BM25Okapi ranking function."""

    def __init__(self, corpus: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.N = len(corpus)
        self.avgdl = sum(len(d) for d in corpus) / max(self.N, 1)
        self.doc_len = [len(d) for d in corpus]
        self.doc_freqs: Dict[str, int] = {}
        self.tf: List[Counter] = []

        for doc in corpus:
            tf = Counter(doc)
            self.tf.append(tf)
            for term in set(doc):
                self.doc_freqs[term] = self.doc_freqs.get(term, 0) + 1

    def _idf(self, term: str) -> float:
        n = self.doc_freqs.get(term, 0)
        return math.log((self.N - n + 0.5) / (n + 0.5) + 1.0)

    def score(self, query_tokens: List[str]) -> List[float]:
        """Return a relevance score for every document in the corpus."""
        scores: List[float] = []
        for idx in range(self.N):
            s = 0.0
            dl = self.doc_len[idx]
            for q in query_tokens:
                tf = self.tf[idx].get(q, 0)
                idf = self._idf(q)
                num = tf * (self.k1 + 1)
                den = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                s += idf * num / den
            scores.append(s)
        return scores


# ─────────────────────────────────────────────
# Report Index (wraps BM25 for report search)
# ─────────────────────────────────────────────
class ReportIndex:
    """
    Searchable index over a list of report metadata dicts.

    Parameters
    ----------
    reports : list of dict
        Each dict should have at least ``Report_Name``.  Optional keys:
        ``Brief_Description``, ``DS_Description``,
        ``Fields_Displayed_on_Report``, ``Fields_Referenced_in_Report``.
    """

    def __init__(self, reports: List[Dict[str, Any]]):
        self.reports = reports
        self._composites = [self._build_composite(r) for r in reports]
        tokenized = [stem_tokenize(c) for c in self._composites]
        self._bm25 = BM25(tokenized, k1=config.BM25_K1, b=config.BM25_B)

    # ── composite text builder ──
    @staticmethod
    def _build_composite(report: Dict[str, Any]) -> str:
        name = report.get("Report_Name", "")
        desc = report.get("Brief_Description", "") or ""
        ds   = report.get("DS_Description", "") or ""
        fd   = report.get("Fields_Displayed_on_Report", "") or ""
        fr   = report.get("Fields_Referenced_in_Report", "") or ""
        ref  = report.get("referenceID", "") or ""

        parts: List[str] = []
        parts.extend([name] * config.NAME_BOOST)
        parts.extend([desc] * config.DESC_BOOST)
        parts.extend([ds]   * config.DS_DESC_BOOST)
        parts.extend([fd]   * config.FIELD_BOOST)
        parts.extend([fr]   * config.FIELD_BOOST)
        if ref:
            parts.append(ref)
        return " ".join(parts)

    # ── search ──
    def search(
        self,
        query: str,
        top_n: int | None = None,
        use_synonyms: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Search the index and return the top-N candidates.

        Returns
        -------
        list of dict
            Each dict contains ``report`` (original metadata),
            ``bm25_score``, and ``bm25_rank``.
        """
        top_n = top_n or config.BM25_TOP_N
        tokens = stem_tokenize(query)
        if use_synonyms:
            tokens = expand_query_with_synonyms(tokens)

        raw_scores = self._bm25.score(tokens)

        ranked = sorted(
            range(len(raw_scores)),
            key=lambda i: raw_scores[i],
            reverse=True,
        )

        results = []
        for rank, idx in enumerate(ranked[:top_n], start=1):
            score = raw_scores[idx]
            if score <= 0:
                break  # No point returning zero-relevance results
            results.append({
                "report": self.reports[idx],
                "bm25_score": round(score, 4),
                "bm25_rank": rank,
            })
        return results
