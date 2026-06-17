"""Shared utilities used across the agent scripts.

Centralises helpers that were previously copy-pasted (e.g. popup, BOM clean).
"""

from __future__ import annotations

import ctypes
import os


# ---------------------------------------------------------------------------
# Windows pop-up
# ---------------------------------------------------------------------------

def popup(title: str, message: str, *, error: bool = False) -> None:
    """Show a native Windows message box (falls back to console if unavailable).

    Set the ``AGENT_NO_POPUP`` env var to skip the blocking dialog in
    automated / non-interactive runs.
    """
    MB_OK = 0x0
    MB_ICONINFO = 0x40
    MB_ICONERROR = 0x10
    MB_TOPMOST = 0x40000
    flags = MB_OK | (MB_ICONERROR if error else MB_ICONINFO) | MB_TOPMOST
    if os.environ.get("AGENT_NO_POPUP"):
        prefix = "ERROR: " if error else ""
        print(f"\n[popup] {prefix}{title}\n{message}")
        return
    try:
        ctypes.windll.user32.MessageBoxW(0, message, title, flags)
    except Exception:  # noqa: BLE001 - not on Windows / no GUI
        prefix = "ERROR: " if error else ""
        print(f"\n{prefix}{title}\n{message}")


# ---------------------------------------------------------------------------
# Input cleaning
# ---------------------------------------------------------------------------

def clean_input(s: str) -> str:
    """Strip a leading UTF-8 BOM (or its cp1252 mojibake), drop non-printable
    chars, and trim whitespace."""
    for bom in ("\ufeff", "ï»¿"):
        if s.startswith(bom):
            s = s[len(bom):]
    return "".join(ch for ch in s if ch.isprintable()).strip()
