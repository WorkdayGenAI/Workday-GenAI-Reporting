"""
evaluation.py — Evaluation harness for the Report Ranking Agent.

Runs 20 predefined test queries across multiple scenarios and prints
Hit@1, Hit@3, MRR metrics with a comparison table and failure analysis.

Run with:  python evaluation.py
"""

import json
import math
from collections import Counter
from typing import Any, Dict, List, Tuple

from stemmer import tokenize as stem_tokenize, tokenize_plain
from synonyms import expand_query_with_synonyms


# ─────────────────────────────────────────────
# BM25 (local copy for standalone evaluation)
# ─────────────────────────────────────────────
class BM25:
    def __init__(self, corpus, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.N = len(corpus)
        self.avgdl = sum(len(d) for d in corpus) / max(self.N, 1)
        self.doc_len = [len(d) for d in corpus]
        self.doc_freqs: Dict[str, int] = {}
        self.tf = []
        for doc in corpus:
            tf = Counter(doc); self.tf.append(tf)
            for t in set(doc):
                self.doc_freqs[t] = self.doc_freqs.get(t, 0) + 1

    def _idf(self, t):
        n = self.doc_freqs.get(t, 0)
        return math.log((self.N - n + 0.5) / (n + 0.5) + 1.0)

    def score(self, qt):
        scores = []
        for i in range(self.N):
            s = 0.0; dl = self.doc_len[i]
            for q in qt:
                tf = self.tf[i].get(q, 0)
                s += self._idf(q) * tf * (self.k1 + 1) / (
                    tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                )
            scores.append(s)
        return scores


# ─────────────────────────────────────────────
# Test data
# ─────────────────────────────────────────────
REPORT_NAMES = [
    "Terminations by Performance",
    "Headcount, Hires and Terminations by Month",
    "Expenses for My Organizations",
    "Headcount by Year (Hires and Promotions)",
    "Bonus and One-time Payments",
    "Terminations",
    "Compensation Changes",
    "Average Performance Ratings by Supervisory Organization Hierarchy",
    "Employee Movement by Organization",
    "Worker and Dependent Details",
]

TEST_CASES: List[Tuple[str, int]] = [
    ("Employee terminations linked to performance metrics", 0),
    ("Impact of performance ratings on termination rates", 0),
    ("Monthly workforce headcount trends by year", 1),
    ("Monthly hiring and termination statistics", 1),
    ("Organizational expense management", 2),
    ("Average organizational expenses", 2),
    ("Annual headcount growth hires promotions", 3),
    ("Yearly workforce expansion and promotion trends", 3),
    ("Bonus and one-time payments this year", 4),
    ("Employee bonus distribution trends", 4),
    ("Termination rates across industries", 5),
    ("Common reasons for employee termination", 5),
    ("Salary adjustment trends", 6),
    ("Compensation change occurred this year", 6),
    ("Average employee performance ratings by department", 7),
    ("Performance rating distribution across organizational hierarchy", 7),
    ("Employee transfers and mobility trends", 8),
    ("Internal workforce movement by organization structure", 8),
    ("Employee and dependents data", 9),
    ("List of worker dependent details", 9),
]


def _load_json_reports(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict):
        for k in raw:
            if isinstance(raw[k], list):
                return {r.get("Report_Name", "").strip(): r for r in raw[k]}
    return {}


def _composite(name: str, lookup: dict) -> str:
    rec = lookup.get(name)
    if rec:
        return " ".join([
            name, name, name,
            rec.get("Brief_Description", "") or "",
            rec.get("DS_Description", "") or "",
            rec.get("Fields_Displayed_on_Report", "") or "",
            rec.get("Fields_Referenced_in_Report", "") or "",
        ])
    return name


# ─────────────────────────────────────────────
# Run a scenario
# ─────────────────────────────────────────────
def run_scenario(corpus_texts, q_tokenizer, c_tokenizer, use_syn=False):
    tc = [c_tokenizer(t) for t in corpus_texts]
    bm25 = BM25(tc)
    results = []
    for query, exp_idx in TEST_CASES:
        qt = q_tokenizer(query)
        if use_syn:
            qt = expand_query_with_synonyms(qt)
        scores = bm25.score(qt)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        cr = ranked.index(exp_idx) + 1
        results.append({"query": query, "expected": REPORT_NAMES[exp_idx],
                        "rank": cr, "hit1": cr == 1, "hit3": cr <= 3})
    return results


def metrics(res):
    t = len(res)
    h1 = sum(1 for r in res if r["hit1"])
    h3 = sum(1 for r in res if r["hit3"])
    mrr = sum(1.0 / r["rank"] for r in res) / t
    return h1, h3, round(mrr, 4), t


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    import os
    json_path = os.path.join(os.path.dirname(__file__), "data", "sample_reports.json")
    lookup = _load_json_reports(json_path) if os.path.exists(json_path) else {}

    names_only = REPORT_NAMES
    full_meta = [_composite(n, lookup) for n in REPORT_NAMES]

    # Scenario A: names only, no stemming, no synonyms
    res_a = run_scenario(names_only, tokenize_plain, tokenize_plain, False)
    # Scenario B: names only + stemming + synonyms
    res_b = run_scenario(names_only, stem_tokenize, stem_tokenize, True)
    # Scenario C: full metadata + stemming + synonyms
    res_c = run_scenario(full_meta, stem_tokenize, stem_tokenize, True)

    ma, mb, mc = metrics(res_a), metrics(res_b), metrics(res_c)

    sep = "=" * 110
    print(sep)
    print("EVALUATION RESULTS — Report Ranking Agent")
    print(sep)

    # Per-query table
    print(f"\n{'#':<3} {'Query':<55} {'A':<6} {'B':<6} {'C':<6}")
    print("-" * 80)
    for i in range(len(TEST_CASES)):
        a, b, c = res_a[i], res_b[i], res_c[i]
        ia = "✅" if a["hit1"] else ("⚠️" if a["hit3"] else "❌")
        ib = "✅" if b["hit1"] else ("⚠️" if b["hit3"] else "❌")
        ic = "✅" if c["hit1"] else ("⚠️" if c["hit3"] else "❌")
        print(f"{i+1:<3} {a['query'][:53]:<55} #{a['rank']}{ia}  #{b['rank']}{ib}  #{c['rank']}{ic}")

    # Summary
    print(f"\n{sep}")
    print("SUMMARY METRICS")
    print(sep)
    print(f"{'Metric':<30} {'A: Baseline':<20} {'B: +Stem+Syn':<20} {'C: +Full Meta':<20}")
    print("-" * 90)
    print(f"{'Hit@1':<30} {ma[0]}/{ma[3]} ({ma[0]/ma[3]*100:.0f}%)        {mb[0]}/{mb[3]} ({mb[0]/mb[3]*100:.0f}%)        {mc[0]}/{mc[3]} ({mc[0]/mc[3]*100:.0f}%)")
    print(f"{'Hit@3':<30} {ma[1]}/{ma[3]} ({ma[1]/ma[3]*100:.0f}%)        {mb[1]}/{mb[3]} ({mb[1]/mb[3]*100:.0f}%)        {mc[1]}/{mc[3]} ({mc[1]/mc[3]*100:.0f}%)")
    print(f"{'MRR':<30} {ma[2]:<18} {mb[2]:<18} {mc[2]}")

    # Failure analysis for Scenario C
    fails = [r for r in res_c if not r["hit1"]]
    print(f"\n{sep}")
    print(f"FAILURE ANALYSIS — Scenario C ({len(fails)} queries not at #1)")
    print(sep)
    for r in fails:
        has_meta = r["expected"] in lookup
        icon = "⚠️" if r["hit3"] else "❌"
        cause = "Missing metadata" if not has_meta else (
            "Close miss (top-3)" if r["hit3"] else "Vocabulary gap"
        )
        print(f"  {icon} \"{r['query'][:60]}\"")
        print(f"     Expected: {r['expected']}  Rank: #{r['rank']}  Cause: {cause}")

    print(f"\n{sep}")
    print("DONE")
    print(sep)


if __name__ == "__main__":
    main()
