"""
report_catalog.py — Load and inspect Workday report metadata.
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Fields we expect in each report record
_KEY_FIELDS = [
    "Report_Name",
    "Brief_Description",
    "DS_Description",
    "Fields_Displayed_on_Report",
    "Fields_Referenced_in_Report",
    "Report_Type",
]


class ReportCatalog:
    """
    Container for report metadata loaded from a JSON file.
    """

    def __init__(self):
        self._reports: List[Dict[str, Any]] = []
        self._by_name: Dict[str, Dict[str, Any]] = {}

    # ── loaders ──
    def load_from_json(self, filepath: str) -> "ReportCatalog":
        """Load reports from a JSON file (single array or wrapped object)."""
        with open(filepath, "r", encoding="utf-8") as f:
            raw = json.load(f)

        if isinstance(raw, list):
            records = raw
        elif isinstance(raw, dict):
            # Try common wrapper keys
            for key in ("Report_Entry", "reports", "data"):
                if key in raw and isinstance(raw[key], list):
                    records = raw[key]
                    break
            else:
                # Use the first list value found
                records = next(
                    (v for v in raw.values() if isinstance(v, list)), [raw]
                )
        else:
            records = [raw]

        self._reports = records
        self._by_name = {
            r.get("Report_Name", "").strip(): r for r in records
        }
        logger.info("Loaded %d reports from %s", len(self._reports), filepath)
        return self

    # ── accessors ──
    def get_all_reports(self) -> List[Dict[str, Any]]:
        return list(self._reports)

    def get_report(self, name: str) -> Optional[Dict[str, Any]]:
        return self._by_name.get(name)

    def __len__(self) -> int:
        return len(self._reports)

    # ── data quality ──
    def data_quality_report(self) -> Dict[str, Any]:
        """
        Return a summary of metadata completeness.
        """
        total = len(self._reports)
        if total == 0:
            return {"total": 0, "message": "No reports loaded."}

        field_counts: Dict[str, int] = {f: 0 for f in _KEY_FIELDS}
        for rpt in self._reports:
            for f in _KEY_FIELDS:
                if rpt.get(f):
                    field_counts[f] += 1

        coverage = {
            f: {
                "present": field_counts[f],
                "missing": total - field_counts[f],
                "pct": round(field_counts[f] / total * 100, 1),
            }
            for f in _KEY_FIELDS
        }

        return {
            "total_reports": total,
            "field_coverage": coverage,
            "fully_complete": sum(
                1
                for r in self._reports
                if all(r.get(f) for f in _KEY_FIELDS)
            ),
        }
