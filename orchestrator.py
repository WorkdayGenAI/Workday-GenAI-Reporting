"""Async orchestrator — 3-agent workflow: Discovery → Migration → Export.

Takes user input **once**, optionally runs the Report Discovery Agent to
find reports by natural-language query, then launches Migration (and
optionally Export) in isolated Playwright BrowserContexts via
``asyncio.gather``.

Workflow:
  1. Discovery — user searches the 11k-report catalog by keyword/query
     OR manually enters report names.
  2. Migration — creates a Configuration Package and migrates the reports.
  3. Export (optional) — downloads the report definitions as Excel.

Run:
    .venv\\Scripts\\python.exe orchestrator.py
"""

from __future__ import annotations

import asyncio
import getpass
import os
import sys
import time

from playwright.async_api import async_playwright

# Config builders from the existing agent scripts (pure-Python, no Playwright).
from run_agent import build_config as build_migration_config
from run_export import build_config as build_export_config

# Async step-execution engine (merged into runner.py).
from runner import run_config_async

# Shared helpers.
from utils import popup, clean_input


# ---------------------------------------------------------------------------
# Discovery Agent integration
# ---------------------------------------------------------------------------

def _run_discovery() -> list[str]:
    """Launch the Report Discovery web UI and wait for the user to select reports.

    Returns a list of selected report names, or an empty list if it timed out.
    """
    try:
        from Workday_Report_Discovery_Agent.api_server import start_server, wait_for_confirmation
        import webbrowser
        
        print("\n  Starting Report Discovery web server on http://127.0.0.1:8000 ...")
        # Start the FastAPI server in a background thread
        start_server(port=8000)
        
        # Automatically open the browser
        url = "http://127.0.0.1:8000"
        print(f"  Opening browser: {url}")
        webbrowser.open(url)
        
        # Block until the user clicks 'Proceed' in the web UI, or timeout (15 mins)
        reports = wait_for_confirmation(timeout=900)
        
        if not reports:
            print("  No reports were selected (or timed out).")
        return reports
        
    except ImportError as exc:
        print(f"\n  ⚠ Discovery server unavailable: {exc}")
        print("    Falling back to manual report entry.\n")
        return []

def _prompt_manual_reports() -> list[str]:
    """Fallback: manually type report names."""
    print(
        "\nEnter the report name(s) to process.\n"
        "  - one per line, OR a single comma-separated line\n"
        "  - press Enter on a blank line when done"
    )
    reports: list[str] = []
    while True:
        line = clean_input(input("  report> "))
        if line == "":
            if reports:
                break
            print("  Please enter at least one report name.")
            continue
        line = line.strip("{}").strip()
        parts = line.split(",") if "," in line else [line]
        for part in parts:
            name = clean_input(part.strip().strip('"').strip("'"))
            if name:
                reports.append(name)

    # de-duplicate while preserving order
    seen: set[str] = set()
    reports = [r for r in reports if not (r in seen or seen.add(r))]
    return reports


# ---------------------------------------------------------------------------
# User input (collected once for all agents)
# ---------------------------------------------------------------------------

def prompt_inputs() -> tuple[str, list[str], bool]:
    """Prompt for industry, report names (via Discovery Web UI or manual), and export toggle.

    Returns ``(industry, reports, run_export)``.
    """
    print("=" * 60)
    print("  Workday Agent Orchestrator")
    print("  Discovery → Migration → Export")
    print("=" * 60)

    industry = ""
    while not industry:
        industry = clean_input(input("\nEnter the Industry name: "))
        if not industry:
            print("  Industry name cannot be empty.")

    # --- Report selection: Discovery UI or Manual ---
    print("\n  How would you like to select reports?")
    print("    1. Search the report catalog in browser (recommended)")
    print("    2. Manually type report names in terminal")
    choice = ""
    while choice not in ("1", "2"):
        choice = clean_input(input("  Choice [1/2]: "))
        if choice not in ("1", "2"):
            print("  Please enter 1 or 2.")

    if choice == "1":
        reports = _run_discovery()
        if not reports:
            print("  No reports selected from web UI. Switching to manual entry.\n")
            reports = _prompt_manual_reports()
    else:
        reports = _prompt_manual_reports()

    # Ask whether to also run the Export agent
    print("\n  Do you also want to download the report definitions as Excel?")
    print("  (This runs the Export agent in parallel with Migration)")
    run_export_choice = ""
    while run_export_choice not in ("y", "n"):
        run_export_choice = clean_input(
            input("  Run Export agent? [y/n]: ")
        ).lower()
        if run_export_choice not in ("y", "n"):
            print("  Please enter 'y' or 'n'.")

    return industry, reports, run_export_choice == "y"

# ---------------------------------------------------------------------------
# Agent wrapper (independent error handling)
# ---------------------------------------------------------------------------

async def _run_agent_task(
    context,
    config: dict,
    agent_name: str,
) -> dict:
    """Run one agent inside its own BrowserContext.

    Wraps :func:`run_config_async` in a ``try/except`` so that a failure in
    one agent never cancels the other.
    """
    start = time.perf_counter()
    print(f"\n{'─' * 50}")
    print(f"  [{agent_name}] STARTED")
    print(f"{'─' * 50}\n")

    try:
        exit_code, error = await run_config_async(
            config, context, agent_name=agent_name,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - start
        print(f"\n[{agent_name}] FATAL ERROR after {elapsed:.1f}s: {exc}",
              file=sys.stderr)
        return {
            "agent": agent_name,
            "exit_code": 1,
            "error": str(exc),
            "elapsed": elapsed,
        }

    elapsed = time.perf_counter() - start
    status = "✓ SUCCESS" if exit_code == 0 else "✗ FAILED"
    print(f"\n[{agent_name}] {status} ({elapsed:.1f}s)")
    return {
        "agent": agent_name,
        "exit_code": exit_code,
        "error": error,
        "elapsed": elapsed,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def async_main() -> int:
    # ── 1. Collect input once ──────────────────────────────────────────────
    industry, reports, run_export = prompt_inputs()

    if not os.environ.get("WD_USER"):
        os.environ["WD_USER"] = input("Workday username: ").strip()
    if not os.environ.get("WD_PASS"):
        os.environ["WD_PASS"] = getpass.getpass("Workday password (hidden): ")

    package_name = f"{industry}_Config_Package"
    mode = "Migration + Export" if run_export else "Migration only"
    print(f"\n  Mode                : {mode}")
    print(f"  Configuration Package : {package_name}")
    print(f"  Reports ({len(reports)})          : {', '.join(reports)}")

    # ── 2. Build configs ──────────────────────────────────────────────────
    migration_config = build_migration_config(industry, reports)
    print(f"\n  Migration steps : {len(migration_config['steps'])}")

    export_config = None
    if run_export:
        export_config = build_export_config(reports)
        print(f"  Export steps    : {len(export_config['steps'])}")

    print(f"\n  Launching {'BOTH agents in parallel' if run_export else 'Migration agent'}…\n")

    # ── 3. Launch browser + context(s) ────────────────────────────────────
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            channel="chrome",
        )

        migration_ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
        )

        tasks = [
            _run_agent_task(migration_ctx, migration_config, "Migration"),
        ]
        contexts = [migration_ctx]

        if run_export and export_config is not None:
            export_ctx = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                accept_downloads=True,
            )
            tasks.append(
                _run_agent_task(export_ctx, export_config, "Export"),
            )
            contexts.append(export_ctx)

        # ── 4. Run agent(s) concurrently ───────────────────────────────────
        results = await asyncio.gather(*tasks)

        # ── 5. Cleanup ────────────────────────────────────────────────────
        for ctx in contexts:
            await ctx.close()
        await browser.close()

    # ── 6. Report results ─────────────────────────────────────────────────
    print(f"\n{'═' * 60}")
    print("  FINAL RESULTS")
    print(f"{'═' * 60}")

    all_ok = True
    for r in results:
        status = "✓ SUCCESS" if r["exit_code"] == 0 else "✗ FAILED"
        print(f"  [{r['agent']:>9}]  {status}  ({r['elapsed']:.1f}s)")
        if r["error"]:
            print(f"              Error : {r['error'][:120]}")
            print(f"              Screenshot : error-{r['agent']}.png")
        if r["exit_code"] != 0:
            all_ok = False

    if run_export:
        print(f"\n  Excel downloads saved to: exported_reports/")

    print(f"{'═' * 60}\n")

    # ── Pop-up summary ────────────────────────────────────────────────────
    agents_label = "Migration + Export" if run_export else "Migration"
    if all_ok:
        msg = (
            f"{agents_label} completed successfully.\n\n"
            f"Configuration Package: {package_name}\n"
            f"Reports: {len(reports)}\n"
            f"  - " + "\n  - ".join(reports)
        )
        if run_export:
            msg += f"\n\nExcel files saved to: exported_reports/"
        popup("Orchestrator — All Done", msg)
    else:
        failed = [r["agent"] for r in results if r["exit_code"] != 0]
        succeeded = [r["agent"] for r in results if r["exit_code"] == 0]
        msg = f"Failed: {', '.join(failed)}\n"
        if succeeded:
            msg += f"Succeeded: {', '.join(succeeded)}\n"
        msg += f"\nConfiguration Package: {package_name}\n"
        msg += "\nSee error-<agent>.png for failure screenshots."
        popup("Orchestrator — Partial Failure", msg, error=True)

    return 0 if all_ok else 1


def main() -> int:
    from utils import ensure_playwright_installed
    ensure_playwright_installed()
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
