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
from datetime import datetime

from playwright.async_api import async_playwright

# Config builders from the existing agent scripts (pure-Python, no Playwright).
from run_agent import build_config as build_migration_config
from run_dashboard_agent import build_config as build_dashboard_config
from run_export import build_config as build_export_config

# Async step-execution engine (merged into runner.py).
from runner import run_config_async

# Shared helpers.
from utils import popup, clean_input

# Styled console output
import console as con


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
        
        con.dim("Starting Report Discovery web server on http://127.0.0.1:8100 ...")
        # Start the FastAPI server in a background thread
        start_server(port=8100)
        
        # Automatically open the browser
        url = "http://127.0.0.1:8100"
        con.dim(f"Opening browser: {url}")
        webbrowser.open(url)
        
        # Block until the user clicks 'Proceed' in the web UI, or timeout (15 mins)
        reports = wait_for_confirmation(timeout=900)
        
        if not reports:
            con.warn("No reports were selected (or timed out).")
        return reports
        
    except ImportError as exc:
        con.warn(f"Discovery server unavailable: {exc}")
        con.dim("Falling back to manual report entry.")
        return []

def _prompt_manual_reports() -> list[str]:
    """Fallback: manually type report names."""
    print()
    con.dim("Enter the report name(s) to process.")
    con.dim("  • one per line, OR a single comma-separated line")
    con.dim("  • press Enter on a blank line when done")
    print()
    reports: list[str] = []
    while True:
        line = clean_input(input(f"  {con.C.B_CYAN}report▸{con.C.RESET} "))
        if line == "":
            if reports:
                break
            con.warn("Please enter at least one report name.")
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
# Startup menu — choose which agent(s) to run
# ---------------------------------------------------------------------------

def _show_main_menu() -> str:
    """Display the startup menu and return the user's choice.

    Returns:
        "1" — Full workflow (Migration + optional Export)
        "2" — Report Migration agent only
        "3" — Dashboard Migration agent only
        "4" — Export (Report Definition) agent only
    """
    con.banner(
        "Workday Report Migration Orchestrator",
        "Discovery  →  Migration  →  Export",
    )

    con.section("Select Workflow")
    print()
    con.menu_option("1", "Full Workflow  (Discovery → Report Config Package → Export)", recommended=True)
    con.menu_option("2", "Report Config Package Agent only")
    con.menu_option("3", "Dashboard Config Package Agent only")
    con.menu_option("4", "Export Definitions Agent only")
    print()
    choice = ""
    while choice not in ("1", "2", "3", "4"):
        choice = clean_input(con.styled_input("Choice [1/2/3/4]: "))
        if choice not in ("1", "2", "3", "4"):
            con.warn("Please enter 1, 2, 3, or 4.")
    return choice


# ---------------------------------------------------------------------------
# Input prompts (adapted per workflow mode)
# ---------------------------------------------------------------------------

def _prompt_reports_selection() -> list[str]:
    """Prompt for report selection via Discovery UI or manual entry."""
    con.section("Report Selection")
    print()
    con.dim("How would you like to select reports?")
    print()
    con.menu_option("1", "Search the report catalog in browser", recommended=True)
    con.menu_option("2", "Manually type report names in terminal")
    print()
    choice = ""
    while choice not in ("1", "2"):
        choice = clean_input(con.styled_input("Choice [1/2]: "))
        if choice not in ("1", "2"):
            con.warn("Please enter 1 or 2.")

    if choice == "1":
        reports = _run_discovery()
        if not reports:
            con.warn("No reports selected from web UI. Switching to manual entry.")
            reports = _prompt_manual_reports()
    else:
        reports = _prompt_manual_reports()
    return reports


def _prompt_credentials() -> None:
    """Prompt for Workday credentials if not already set via env."""
    if not os.environ.get("WD_USER"):
        print()
        os.environ["WD_USER"] = clean_input(con.styled_input("Workday username: "))
    if not os.environ.get("WD_PASS"):
        os.environ["WD_PASS"] = getpass.getpass(
            f"  {con.C.B_CYAN}{con.SYM_ARROW}{con.C.RESET} {con.C.BOLD}Workday password (hidden): {con.C.RESET}"
        )


def _generate_package_name(industry: str) -> str:
    """Generate a unique Configuration Package name with today's date.

    Format: {Industry}_Config_Package_{MM/DD/YYYY}
    Example: Healthcare_Config_Package_07/02/2026
    """
    date_str = datetime.now().strftime("%m/%d/%Y")
    return f"{industry}_Config_Package_{date_str}"


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
    con.agent_start(agent_name, len(config["steps"]))

    try:
        exit_code, error = await run_config_async(
            config, context, agent_name=agent_name,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - start
        con.agent_done(agent_name, elapsed, ok=False)
        con.fail(f"FATAL ERROR after {elapsed:.1f}s: {exc}")
        return {
            "agent": agent_name,
            "exit_code": 1,
            "error": str(exc),
            "elapsed": elapsed,
        }

    elapsed = time.perf_counter() - start
    con.agent_done(agent_name, elapsed, ok=(exit_code == 0))
    return {
        "agent": agent_name,
        "exit_code": exit_code,
        "error": error,
        "elapsed": elapsed,
    }


# ---------------------------------------------------------------------------
# Workflow: Full (Migration + optional Export)
# ---------------------------------------------------------------------------

async def _workflow_full() -> int:
    """Full workflow: collect industry + reports + export toggle, run agents."""
    # ── Configuration ─────────────────────────────────────────────────────
    con.section("Configuration")
    print()
    industry = ""
    while not industry:
        industry = clean_input(con.styled_input("Industry name: "))
        if not industry:
            con.warn("Industry name cannot be empty.")

    print()
    reports = _prompt_reports_selection()

    # ── Export toggle ─────────────────────────────────────────────────────
    print()
    con.section("Export Options")
    print()
    con.dim("Download report definitions as Excel alongside migration?")
    print()
    con.menu_option("y", "Yes — run Export agent in parallel")
    con.menu_option("n", "No  — migration only")
    print()
    run_export_choice = ""
    while run_export_choice not in ("y", "n"):
        run_export_choice = clean_input(
            con.styled_input("Run Export agent? [y/n]: ")
        ).lower()
        if run_export_choice not in ("y", "n"):
            con.warn("Please enter 'y' or 'n'.")
    run_export = run_export_choice == "y"

    # ── Credentials ──────────────────────────────────────────────────────
    _prompt_credentials()

    package_name = _generate_package_name(industry)
    mode = "Migration + Export" if run_export else "Migration only"

    # ── Summary ──────────────────────────────────────────────────────────
    print()
    con.section("Launch Summary")
    print()
    con.info("Mode", mode)
    con.info("Config Package", package_name)
    con.info("Reports", f"{len(reports)} selected")
    for r in reports:
        con.bullet(r)

    # ── Build configs ────────────────────────────────────────────────────
    migration_config = build_migration_config(industry, reports)
    print()
    con.info("Migration steps", str(len(migration_config['steps'])))

    export_config = None
    if run_export:
        export_config = build_export_config(reports)
        con.info("Export steps", str(len(export_config['steps'])))

    print()
    if run_export:
        con.success("Launching BOTH agents in parallel …")
    else:
        con.success("Launching Migration agent …")
    print()

    # ── Launch browser + context(s) ──────────────────────────────────────
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="chrome")

        migration_ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900}, accept_downloads=True,
        )
        tasks = [_run_agent_task(migration_ctx, migration_config, "Report Config Package")]
        contexts = [migration_ctx]

        if run_export and export_config is not None:
            export_ctx = await browser.new_context(
                viewport={"width": 1440, "height": 900}, accept_downloads=True,
            )
            tasks.append(_run_agent_task(export_ctx, export_config, "Export"))
            contexts.append(export_ctx)

        results = await asyncio.gather(*tasks)

        for ctx in contexts:
            await ctx.close()
        await browser.close()

    # ── Report results ───────────────────────────────────────────────────
    return _print_results(results, run_export, package_name, reports)


# ---------------------------------------------------------------------------
# Workflow: Migration only
# ---------------------------------------------------------------------------

async def _workflow_migration_only() -> int:
    """Run Migration agent only (no Export)."""
    # ── Configuration ────────────────────────────────────────────────────
    con.section("Configuration")
    print()
    industry = ""
    while not industry:
        industry = clean_input(con.styled_input("Industry name: "))
        if not industry:
            con.warn("Industry name cannot be empty.")

    print()
    reports = _prompt_reports_selection()
    _prompt_credentials()

    package_name = _generate_package_name(industry)

    # ── Summary ──────────────────────────────────────────────────────────
    print()
    con.section("Launch Summary")
    print()
    con.info("Mode", "Migration only")
    con.info("Config Package", package_name)
    con.info("Reports", f"{len(reports)} selected")
    for r in reports:
        con.bullet(r)

    migration_config = build_migration_config(industry, reports)
    print()
    con.info("Migration steps", str(len(migration_config['steps'])))
    print()
    con.success("Launching Migration agent …")
    print()

    # ── Launch ───────────────────────────────────────────────────────────
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="chrome")
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900}, accept_downloads=True,
        )
        results = [await _run_agent_task(ctx, migration_config, "Report Config Package")]
        await ctx.close()
        await browser.close()

    return _print_results(results, False, package_name, reports)


# ---------------------------------------------------------------------------
# Workflow: Dashboard Migration only
# ---------------------------------------------------------------------------

def _prompt_manual_dashboards() -> list[str]:
    """Prompt the user to manually type dashboard names."""
    print()
    con.dim("Enter the dashboard name(s) to migrate.")
    con.dim("  • one per line, OR a single comma-separated line")
    con.dim("  • press Enter on a blank line when done")
    print()
    dashboards: list[str] = []
    while True:
        line = clean_input(input(f"  {con.C.B_CYAN}dashboard▸{con.C.RESET} "))
        if line == "":
            if dashboards:
                break
            con.warn("Please enter at least one dashboard name.")
            continue
        line = line.strip("{}").strip()
        parts = line.split(",") if "," in line else [line]
        for part in parts:
            name = clean_input(part.strip().strip('"').strip("'"))
            if name:
                dashboards.append(name)

    # de-duplicate while preserving order
    seen: set[str] = set()
    dashboards = [d for d in dashboards if not (d in seen or seen.add(d))]
    return dashboards


async def _workflow_dashboard_only() -> int:
    """Run Dashboard Migration agent only."""
    # ── Configuration ────────────────────────────────────────────────────
    con.section("Configuration")
    print()
    industry = ""
    while not industry:
        industry = clean_input(con.styled_input("Industry name: "))
        if not industry:
            con.warn("Industry name cannot be empty.")

    print()
    con.section("Dashboard Selection")
    dashboards = _prompt_manual_dashboards()
    _prompt_credentials()

    package_name = _generate_package_name(industry).replace(
        "_Config_Package_", "_Dashboard_Config_Package_"
    )

    # ── Summary ──────────────────────────────────────────────────────────
    print()
    con.section("Launch Summary")
    print()
    con.info("Mode", "Dashboard Migration only")
    con.info("Config Package", package_name)
    con.info("Dashboards", f"{len(dashboards)} selected")
    for d in dashboards:
        con.bullet(d)

    dashboard_config = build_dashboard_config(industry, dashboards)
    print()
    con.info("Dashboard Migration steps", str(len(dashboard_config['steps'])))
    print()
    con.success("Launching Dashboard Migration agent …")
    print()

    # ── Launch ───────────────────────────────────────────────────────────
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="chrome")
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900}, accept_downloads=True,
        )
        results = [await _run_agent_task(ctx, dashboard_config, "Dashboard Config Package")]
        await ctx.close()
        await browser.close()

    return _print_results(results, False, package_name, dashboards)


# ---------------------------------------------------------------------------
# Workflow: Export only
# ---------------------------------------------------------------------------

async def _workflow_export_only() -> int:
    """Run Export (Report Definition) agent only (no Migration)."""
    # ── Configuration ────────────────────────────────────────────────────
    con.section("Report Selection")
    print()
    reports = _prompt_reports_selection()
    _prompt_credentials()

    # ── Summary ──────────────────────────────────────────────────────────
    print()
    con.section("Launch Summary")
    print()
    con.info("Mode", "Export only (Report Definitions)")
    con.info("Reports", f"{len(reports)} selected")
    for r in reports:
        con.bullet(r)

    export_config = build_export_config(reports)
    print()
    con.info("Export steps", str(len(export_config['steps'])))
    print()
    con.success("Launching Export agent …")
    print()

    # ── Launch ───────────────────────────────────────────────────────────
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="chrome")
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900}, accept_downloads=True,
        )
        results = [await _run_agent_task(ctx, export_config, "Export")]
        await ctx.close()
        await browser.close()

    return _print_results(results, True, None, reports)


# ---------------------------------------------------------------------------
# Shared results display
# ---------------------------------------------------------------------------

def _print_results(
    results: list[dict],
    has_export: bool,
    package_name: str | None,
    reports: list[str],
) -> int:
    """Print the final results table and pop-up summary. Returns exit code."""
    con.results_header()

    all_ok = True
    for r in results:
        ok = r["exit_code"] == 0
        con.results_row(r["agent"], ok, r["elapsed"], r.get("error"))
        if not ok:
            all_ok = False

    extra = ""
    if has_export:
        extra = "Excel downloads → exported_reports/"
    con.results_footer(extra)

    # ── Pop-up summary ────────────────────────────────────────────────────
    agent_names = [r["agent"] for r in results]
    agents_label = " + ".join(agent_names)

    if all_ok:
        msg = f"{agents_label} completed successfully.\n\n"
        if package_name:
            msg += f"Configuration Package: {package_name}\n"
        msg += f"Reports: {len(reports)}\n"
        msg += "  - " + "\n  - ".join(reports)
        if has_export:
            msg += "\n\nExcel files saved to: exported_reports/"
        popup("Orchestrator — All Done", msg)
    else:
        failed = [r["agent"] for r in results if r["exit_code"] != 0]
        succeeded = [r["agent"] for r in results if r["exit_code"] == 0]
        msg = f"Failed: {', '.join(failed)}\n"
        if succeeded:
            msg += f"Succeeded: {', '.join(succeeded)}\n"
        if package_name:
            msg += f"\nConfiguration Package: {package_name}\n"
        msg += "\nSee error-<agent>.png for failure screenshots."
        popup("Orchestrator — Partial Failure", msg, error=True)

    return 0 if all_ok else 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def async_main() -> int:
    """CLI entry point (used with --cli flag or as fallback)."""
    workflow = _show_main_menu()

    if workflow == "1":
        return await _workflow_full()
    elif workflow == "2":
        return await _workflow_migration_only()
    elif workflow == "3":
        return await _workflow_dashboard_only()
    else:
        return await _workflow_export_only()


def main() -> int:
    from utils import ensure_env_file, ensure_playwright_installed
    ensure_env_file()
    ensure_playwright_installed()

    # Check for --cli flag to use the old terminal menu
    if "--cli" in sys.argv:
        con.dim("Starting in CLI mode…")
        return asyncio.run(async_main())

    # Default: launch the web UI
    con.section("Web UI")
    print()
    con.info("Mode", "Web Dashboard")
    con.dim("Starting Orchestrator Web UI on http://127.0.0.1:8050 …")
    con.dim("The browser will open automatically.")
    con.dim("Use --cli flag to use the terminal menu instead.")
    print()

    from orchestrator_ui.server import start_orchestrator_server
    start_orchestrator_server(port=8050)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
