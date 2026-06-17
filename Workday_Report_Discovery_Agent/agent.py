"""
agent.py — Main orchestrator for the Report Discovery Agent.

Usage
-----
>>> from agent import ReportDiscoveryAgent
>>> agent = ReportDiscoveryAgent("data/sample_reports.json")
>>> results = agent.search("I want a report that gives pre-hire details")
"""

import logging
from typing import Any, Dict, List, Optional

import config
from report_catalog import ReportCatalog
from bm25_engine import ReportIndex
from llm_scorer import LLMScorer

logger = logging.getLogger(__name__)


class ReportDiscoveryAgent:
    """
    Two-stage pipeline: BM25 retrieval → LLM scoring.

    Parameters
    ----------
    catalog_path : str
        Path to the JSON report catalog.
    openai_client : optional
        Pre-initialised ``openai.OpenAI`` client.  If omitted the agent
        attempts to create one from ``config.OPENAI_API_KEY``.
    """

    def __init__(
        self,
        catalog_path: str | None = None,
        openai_client: Any = None,
    ):
        # Load catalog
        self.catalog = ReportCatalog()
        self.catalog.load_from_json(catalog_path or config.DEFAULT_CATALOG_PATH)
        logger.info("Catalog loaded: %d reports", len(self.catalog))

        # Build BM25 index
        self.index = ReportIndex(self.catalog.get_all_reports())
        logger.info("BM25 index built.")

        # Initialise LLM scorer
        client = openai_client or self._try_create_client()
        self.scorer = LLMScorer(client=client)

    # ── try to create OpenAI client ──
    @staticmethod
    def _try_create_client():
        if not config.OPENAI_API_KEY:
            logger.warning(
                "OPENAI_API_KEY not set — LLM scoring disabled, using BM25 only."
            )
            return None
        try:
            from openai import OpenAI
            kwargs = {"api_key": config.OPENAI_API_KEY}
            if config.OPENAI_BASE_URL:
                kwargs["base_url"] = config.OPENAI_BASE_URL
            return OpenAI(**kwargs)
        except ImportError:
            logger.warning("openai package not installed; LLM scoring disabled.")
            return None

    # ── main search ──
    def search(
        self,
        query: str,
        bm25_top_n: int | None = None,
        llm_top_k: int | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Run the full pipeline: BM25 retrieval → LLM scoring.

        Parameters
        ----------
        query : str
            Natural-language user query.
        bm25_top_n : int
            Override for number of BM25 candidates.
        llm_top_k : int
            Override for number of final results.

        Returns
        -------
        list of dict
            Final ranked results with scores and explanations.
        """
        # Stage 1: BM25
        candidates = self.index.search(query, top_n=bm25_top_n)
        logger.info("BM25 returned %d candidates for query: %s", len(candidates), query)

        # Stage 2: LLM
        results = self.scorer.score_candidates(
            query, candidates, top_k=llm_top_k
        )
        logger.info("LLM scored %d results.", len(results))

        return results

    # ── BM25-only search (no LLM) ──
    def search_bm25_only(
        self, query: str, top_n: int | None = None
    ) -> List[Dict[str, Any]]:
        """Return BM25 results without LLM re-ranking."""
        candidates = self.index.search(query, top_n=top_n or config.LLM_TOP_K)
        return [
            {
                "report_name": c["report"].get("Report_Name", "Unknown"),
                "score": c["bm25_score"],
                "band": "N/A",
                "explanation": "Ranked by BM25 keyword relevance.",
                "report": c["report"],
                "bm25_score": c["bm25_score"],
            }
            for c in candidates
        ]

    # ── format ──
    @staticmethod
    def format_results(results: List[Dict[str, Any]]) -> str:
        """Pretty-print results as a string."""
        lines = []
        for i, r in enumerate(results, 1):
            band = r.get("band", "N/A")
            icon = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}.get(band, "⚪")
            lines.append(
                f"{icon} #{i}  [{band}]  {r['report_name']}  "
                f"(Score: {r['score']})"
            )
            lines.append(f"      Why: {r.get('explanation', 'N/A')}")
            desc = r.get("report", {}).get("Brief_Description")
            if desc:
                lines.append(f"      Description: {desc[:120]}...")
            lines.append("")
        return "\n".join(lines)
