"""
llm_scorer.py — LLM-based candidate re-ranker.

Sends the BM25 shortlist to an LLM (via OpenAI-compatible API) and
receives structured scores + explanations.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import config

logger = logging.getLogger(__name__)


class LLMScorer:
    """
    Score and re-rank BM25 candidates using a large language model.

    Parameters
    ----------
    client : openai.OpenAI | None
        An initialised OpenAI client.  If *None*, the scorer falls back
        to returning BM25 order with a warning.
    model : str
        Model name, e.g. ``"gpt-4o"``.
    """

    def __init__(self, client: Any = None, model: str | None = None):
        self.client = client
        self.model = model or config.MODEL_NAME
        self._prompt_template = self._load_prompt_template()

    # ── load prompt ──
    @staticmethod
    def _load_prompt_template() -> str:
        try:
            with open(config.PROMPT_TEMPLATE_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning("Prompt template not found; using built-in default.")
            return (
                "You are a Workday Report Discovery Agent.\n"
                "Score each candidate report 0-100 against the user query.\n"
                "Return a JSON array sorted by score descending.\n"
                "Each element: {rank, report_name, score, band, explanation}.\n"
                "Bands: High (75-100), Medium (40-74), Low (0-39).\n"
                "Ground every explanation in the provided metadata only."
            )

    # ── build prompt ──
    def _build_prompt(
        self, query: str, candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        candidate_text = ""
        for i, c in enumerate(candidates, 1):
            rpt = c["report"]
            candidate_text += f"\n--- Candidate {i} ---\n"
            candidate_text += f"Report Name: {rpt.get('Report_Name', 'N/A')}\n"
            candidate_text += f"Report Type: {rpt.get('Report_Type', 'N/A')}\n"
            candidate_text += f"Description: {rpt.get('Brief_Description') or 'NOT AVAILABLE'}\n"
            candidate_text += f"Data Source: {(rpt.get('DS_Description') or 'N/A')[:300]}\n"
            candidate_text += f"Fields Displayed: {(rpt.get('Fields_Displayed_on_Report') or 'N/A')[:300]}\n"
            candidate_text += f"Fields Referenced: {(rpt.get('Fields_Referenced_in_Report') or 'N/A')[:300]}\n"

        user_msg = (
            f'User Query: "{query}"\n\n'
            f"Candidate Reports:\n{candidate_text}"
        )

        return [
            {"role": "system", "content": self._prompt_template},
            {"role": "user", "content": user_msg},
        ]

    # ── call LLM ──
    def score_candidates(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Score and re-rank candidates using the LLM.

        Parameters
        ----------
        query : str
            The original user query.
        candidates : list of dict
            Output from ``ReportIndex.search()``.
        top_k : int
            Number of final results to return.

        Returns
        -------
        list of dict
            Sorted by LLM relevance score, each containing
            ``report_name``, ``score``, ``band``, ``explanation``,
            and the original ``report`` metadata.
        """
        top_k = top_k or config.LLM_TOP_K

        # ── Fallback if no client ──
        if self.client is None:
            logger.warning("No LLM client configured; returning BM25 order.")
            return self._fallback(candidates, top_k)

        # Cap candidates sent to LLM to avoid token limit issues
        max_llm_candidates = min(len(candidates), 20)
        llm_candidates = candidates[:max_llm_candidates]

        messages = self._build_prompt(query, llm_candidates)

        try:
            # Don't use response_format — not all models support it
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.0,
            )
            content = response.choices[0].message.content
            parsed = self._extract_json(content)

            # Accept both {"results": [...]} and bare [...]
            if isinstance(parsed, dict):
                scored = parsed.get("results", parsed.get("candidates", []))
            elif isinstance(parsed, list):
                scored = parsed
            else:
                raise ValueError("Unexpected LLM response format")

            # Merge back original report metadata
            name_to_cand = {
                c["report"]["Report_Name"]: c for c in llm_candidates
            }
            enriched = []
            for item in scored[:top_k]:
                rname = item.get("report_name", "")
                orig = name_to_cand.get(rname, {})
                enriched.append({
                    "report_name": rname,
                    "score": item.get("score", 0),
                    "band": item.get("band", "Low"),
                    "explanation": item.get("explanation", item.get("why", "")),
                    "report": orig.get("report", {}),
                    "bm25_score": orig.get("bm25_score", 0),
                })
            return enriched

        except Exception as exc:
            logger.error("LLM scoring failed: %s — falling back to BM25 order.", exc)
            return self._fallback(candidates, top_k)

    # ── extract JSON from LLM response (handles markdown-wrapped JSON) ──
    @staticmethod
    def _extract_json(content: str) -> Any:
        """Try direct JSON parse, then extract from markdown code fences."""
        import re
        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        # Try extracting from ```json ... ``` blocks
        match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```", content)
        if match:
            return json.loads(match.group(1))
        # Try finding first { or [ to end of content
        for i, ch in enumerate(content):
            if ch in ('{', '['):
                try:
                    return json.loads(content[i:])
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"Could not extract JSON from LLM response: {content[:200]}")

    # ── fallback ──
    @staticmethod
    def _fallback(
        candidates: List[Dict[str, Any]], top_k: int
    ) -> List[Dict[str, Any]]:
        results = []
        for c in candidates[:top_k]:
            rpt = c["report"]
            results.append({
                "report_name": rpt.get("Report_Name", "Unknown"),
                "score": round(c["bm25_score"], 2),
                "band": "N/A",
                "explanation": "LLM unavailable — ranked by BM25 keyword relevance only.",
                "report": rpt,
                "bm25_score": c["bm25_score"],
            })
        return results
