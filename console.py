"""Console styling for the Reporting Orchestrator.

Provides ANSI-coloured, Unicode-box-drawing output that works on
Windows 10+ Terminal, PowerShell 7, and the legacy ``cmd.exe`` console
(where we enable VT processing automatically).

All output flows through helpers here so the visual language is consistent
across orchestrator.py, runner.py, and utils.py.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime

# ── Enable ANSI/VT100 on Windows cmd.exe ─────────────────────────────────────

def _enable_vt_mode() -> None:
    """Enable Virtual Terminal Processing on Windows so ANSI codes work."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:  # noqa: BLE001
        pass  # Silently degrade — colors just won't show


def _force_utf8() -> None:
    """Reconfigure stdout/stderr to UTF-8 so box-drawing chars render on Windows."""
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


_enable_vt_mode()
_force_utf8()


# ── ANSI Escape Codes ────────────────────────────────────────────────────────

class C:
    """Colour / style constants.  ``C.RESET`` turns everything off."""
    RESET       = "\033[0m"
    BOLD        = "\033[1m"
    DIM         = "\033[2m"
    ITALIC      = "\033[3m"
    UNDERLINE   = "\033[4m"

    # Foreground
    BLACK       = "\033[30m"
    RED         = "\033[31m"
    GREEN       = "\033[32m"
    YELLOW      = "\033[33m"
    BLUE        = "\033[34m"
    MAGENTA     = "\033[35m"
    CYAN        = "\033[36m"
    WHITE       = "\033[37m"

    # Bright foreground
    B_BLACK     = "\033[90m"
    B_RED       = "\033[91m"
    B_GREEN     = "\033[92m"
    B_YELLOW    = "\033[93m"
    B_BLUE      = "\033[94m"
    B_MAGENTA   = "\033[95m"
    B_CYAN      = "\033[96m"
    B_WHITE     = "\033[97m"

    # Background
    BG_BLACK    = "\033[40m"
    BG_BLUE     = "\033[44m"
    BG_CYAN     = "\033[46m"
    BG_WHITE    = "\033[47m"


# ── Box-drawing characters ───────────────────────────────────────────────────

# Heavy box (double lines for major sections)
BOX_TL = "╔"
BOX_TR = "╗"
BOX_BL = "╚"
BOX_BR = "╝"
BOX_H  = "═"
BOX_V  = "║"
BOX_LT = "╠"
BOX_RT = "╣"

# Light box (single lines for sub-sections)
L_TL = "┌"
L_TR = "┐"
L_BL = "└"
L_BR = "┘"
L_H  = "─"
L_V  = "│"
L_LT = "├"
L_RT = "┤"

# Symbols
SYM_CHECK   = "✓"
SYM_CROSS   = "✗"
SYM_ARROW   = "▸"
SYM_DOT     = "●"
SYM_CIRCLE  = "○"
SYM_GEAR    = "⚙"
SYM_ROCKET  = "🚀"
SYM_WARN    = "⚠"
SYM_INFO    = "ℹ"
SYM_STAR    = "★"


# ── Width constant ───────────────────────────────────────────────────────────

W = 64  # standard box width (inner content is W-4 for padded lines)


# ── Low-level line helpers ───────────────────────────────────────────────────

import re

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _visible_len(s: str) -> int:
    """Return the visible (printed) length of a string, ignoring ANSI escapes."""
    return len(_ANSI_RE.sub("", s))


def _hline(left: str, fill: str, right: str, width: int = W) -> str:
    return f"{left}{fill * (width - 2)}{right}"


def _padline(text: str, width: int = W, left: str = BOX_V, right: str = BOX_V) -> str:
    """Centre text inside a bordered line (ANSI-aware)."""
    inner = width - 4  # 2 border chars + 2 spaces
    vis = _visible_len(text)
    pad_total = max(inner - vis, 0)
    pad_left = pad_total // 2
    pad_right = pad_total - pad_left
    return f"{left} {' ' * pad_left}{text}{' ' * pad_right} {right}"


def _leftline(text: str, width: int = W, left: str = BOX_V, right: str = BOX_V) -> str:
    """Left-align text inside a bordered line (ANSI-aware)."""
    inner = width - 4
    vis = _visible_len(text)
    pad = max(inner - vis, 0)
    return f"{left} {text}{' ' * pad} {right}"


# ── High-level section helpers ───────────────────────────────────────────────

def banner(title: str, subtitle: str = "", colour: str = C.B_CYAN) -> None:
    """Print the main application banner (heavy box, coloured)."""
    print()
    print(f"{colour}{_hline(BOX_TL, BOX_H, BOX_TR)}{C.RESET}")
    print(f"{colour}{_padline('')}{C.RESET}")
    print(f"{colour}{_padline(f'{C.BOLD}{title}{C.RESET}{colour}')}{C.RESET}")
    if subtitle:
        print(f"{colour}{_padline(subtitle)}{C.RESET}")
    print(f"{colour}{_padline('')}{C.RESET}")
    ts = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    print(f"{colour}{_padline(f'{C.DIM}{ts}{C.RESET}{colour}')}{C.RESET}")
    print(f"{colour}{_hline(BOX_BL, BOX_H, BOX_BR)}{C.RESET}")
    print()


def section(title: str, colour: str = C.B_BLUE) -> None:
    """Print a section header (light box)."""
    inner = W - 6
    title_vis = len(title)
    pad = max(inner - 2 - title_vis, 0)
    print()
    print(f"{colour}  {L_TL}{L_H * inner}{L_TR}{C.RESET}")
    print(f"{colour}  {L_V} {C.BOLD}{title}{C.RESET}{colour}{' ' * pad}{L_V}{C.RESET}")
    print(f"{colour}  {L_BL}{L_H * inner}{L_BR}{C.RESET}")


def divider(colour: str = C.B_BLACK) -> None:
    """Print a thin horizontal divider."""
    print(f"{colour}  {'·' * (W - 4)}{C.RESET}")


def info(label: str, value: str, colour: str = C.CYAN) -> None:
    """Print a key : value pair."""
    print(f"  {colour}{C.BOLD}{label:<22}{C.RESET}{C.WHITE}{value}{C.RESET}")


def bullet(text: str, colour: str = C.B_CYAN) -> None:
    """Print a bullet point."""
    print(f"  {colour}{SYM_ARROW}{C.RESET} {text}")


def success(text: str) -> None:
    print(f"  {C.B_GREEN}{SYM_CHECK}{C.RESET} {C.GREEN}{text}{C.RESET}")


def fail(text: str) -> None:
    print(f"  {C.B_RED}{SYM_CROSS}{C.RESET} {C.RED}{text}{C.RESET}")


def warn(text: str) -> None:
    print(f"  {C.B_YELLOW}{SYM_WARN}{C.RESET} {C.YELLOW}{text}{C.RESET}")


def dim(text: str) -> None:
    print(f"  {C.DIM}{text}{C.RESET}")


# ── Agent step logging ───────────────────────────────────────────────────────

def step_log(agent: str, index: int, label: str, result: str) -> None:
    """Log an individual step execution — used by runner.py."""
    agent_colour = C.B_CYAN if agent == "Migration" else C.B_MAGENTA
    idx = f"{C.DIM}[{index:>3}]{C.RESET}"
    tag = f"{agent_colour}{C.BOLD}{agent:>9}{C.RESET}"
    print(f"  {tag} {idx} {C.DIM}{label}{C.RESET}")


def step_skip(agent: str, index: int, label: str, reason: str = "optional") -> None:
    """Log a skipped step."""
    agent_colour = C.B_CYAN if agent == "Migration" else C.B_MAGENTA
    idx = f"{C.DIM}[{index:>3}]{C.RESET}"
    tag = f"{agent_colour}{C.BOLD}{agent:>9}{C.RESET}"
    print(f"  {tag} {idx} {C.DIM}{label}: {C.YELLOW}skipped ({reason}){C.RESET}")


def step_error(agent: str, index: int, label: str, error_msg: str) -> None:
    """Log a failed step."""
    agent_colour = C.B_CYAN if agent == "Migration" else C.B_MAGENTA
    idx = f"{C.DIM}[{index:>3}]{C.RESET}"
    tag = f"{agent_colour}{C.BOLD}{agent:>9}{C.RESET}"
    print(f"  {tag} {idx} {C.RED}{SYM_CROSS} {label}: {error_msg}{C.RESET}")


# ── Agent lifecycle banners ──────────────────────────────────────────────────

def agent_start(name: str, step_count: int) -> None:
    """Print when an agent starts running."""
    colour = C.B_CYAN if name == "Migration" else C.B_MAGENTA
    inner = W - 6
    header_text = f"{name.upper()} AGENT"
    header_pad = max(inner - 5 - len(header_text), 0)  # 5 = "─── " + " "
    info_text = f"{step_count} steps queued"
    info_pad = max(inner - 2 - len(info_text), 0)
    print()
    print(f"{colour}  {L_TL}{L_H * 3} {C.BOLD}{header_text}{C.RESET}{colour} {L_H * header_pad}{L_TR}{C.RESET}")
    print(f"{colour}  {L_V}{C.RESET}  {C.DIM}{info_text}{C.RESET}{colour}{' ' * info_pad}{L_V}{C.RESET}")
    print(f"{colour}  {L_BL}{L_H * inner}{L_BR}{C.RESET}")
    print()


def agent_done(name: str, elapsed: float, ok: bool) -> None:
    """Print when an agent finishes."""
    colour = C.B_GREEN if ok else C.B_RED
    sym = SYM_CHECK if ok else SYM_CROSS
    status = "COMPLETED" if ok else "FAILED"
    print()
    print(f"{colour}  {sym} {C.BOLD}{name}{C.RESET}{colour} {status} {C.DIM}({elapsed:.1f}s){C.RESET}")


# ── Results table ────────────────────────────────────────────────────────────

def results_header() -> None:
    """Print the final results header."""
    print()
    print(f"{C.B_WHITE}{C.BOLD}{_hline(BOX_TL, BOX_H, BOX_TR)}{C.RESET}")
    print(f"{C.B_WHITE}{C.BOLD}{_padline('FINAL RESULTS')}{C.RESET}")
    print(f"{C.B_WHITE}{C.BOLD}{_hline(BOX_LT, BOX_H, BOX_RT)}{C.RESET}")


def results_row(agent: str, ok: bool, elapsed: float, error: str | None = None) -> None:
    """Print one row in the results table."""
    sym = f"{C.B_GREEN}{SYM_CHECK}" if ok else f"{C.B_RED}{SYM_CROSS}"
    status_text = f"{C.GREEN}SUCCESS" if ok else f"{C.RED}FAILED"
    time_str = f"({elapsed:.1f}s)"
    # Build content and measure visible width
    content = f"  {sym}{C.RESET}  {C.BOLD}{agent}{C.RESET}  {status_text}{C.RESET}  {C.DIM}{time_str}{C.RESET}"
    vis = _visible_len(content)
    inner = W - 2  # inside the two ║ borders
    pad = max(inner - vis, 0)
    print(f"{C.B_WHITE}{BOX_V}{C.RESET}{content}{' ' * pad}{C.B_WHITE}{BOX_V}{C.RESET}")
    if error:
        err_content = f"    {C.DIM}Error: {error[:50]}{C.RESET}"
        err_vis = _visible_len(err_content)
        err_pad = max(inner - err_vis, 0)
        print(f"{C.B_WHITE}{BOX_V}{C.RESET}{err_content}{' ' * err_pad}{C.B_WHITE}{BOX_V}{C.RESET}")


def results_footer(extra: str = "") -> None:
    """Close the results table."""
    if extra:
        content = f"  {C.DIM}{extra}{C.RESET}"
        vis = _visible_len(content)
        inner = W - 2
        pad = max(inner - vis, 0)
        print(f"{C.B_WHITE}{BOX_V}{C.RESET}{content}{' ' * pad}{C.B_WHITE}{BOX_V}{C.RESET}")
    print(f"{C.B_WHITE}{C.BOLD}{_hline(BOX_BL, BOX_H, BOX_BR)}{C.RESET}")
    print()


# ── Prompt styling ───────────────────────────────────────────────────────────

def styled_input(prompt: str) -> str:
    """Show a styled input prompt and return the stripped result."""
    return input(f"  {C.B_CYAN}{SYM_ARROW}{C.RESET} {C.BOLD}{prompt}{C.RESET}").strip()


def menu_option(key: str, text: str, recommended: bool = False) -> None:
    """Print a numbered menu option."""
    rec = f" {C.B_GREEN}(recommended){C.RESET}" if recommended else ""
    print(f"    {C.B_CYAN}{C.BOLD}[{key}]{C.RESET} {text}{rec}")
