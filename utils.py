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


# ---------------------------------------------------------------------------
# Path Resolution & Environment for PyInstaller
# ---------------------------------------------------------------------------

import sys
import subprocess

def get_bundled_dir() -> str:
    """Return the path to bundled assets (sys._MEIPASS if frozen, else local dir)."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def get_user_dir() -> str:
    """Return the path where the executable is physically located, or local dir."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def ensure_playwright_installed() -> None:
    """Ensure the Playwright Chromium browser is installed on the user's system."""
    import sys
    from playwright._impl._driver import compute_driver_executable, get_driver_env

    # We check if it's already installed by looking for the browser path.
    # But a simple way is just to run `install chromium` unconditionally. Playwright 
    # handles the cache and skips download if already present.
    try:
        driver_executable = compute_driver_executable()
        env = get_driver_env()
        print("Ensuring Playwright Chromium is installed (this may take a minute on first run)...")
        # Run the node-based playwright install script bundled with playwright package
        subprocess.run([driver_executable, "install", "chromium"], env=env, check=True)
    except Exception as e:
        print(f"Warning: Failed to ensure Playwright browsers are installed: {e}", file=sys.stderr)
