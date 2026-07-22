"""Orchestrator Web UI — FastAPI server.

Serves the single-page web dashboard and provides REST API + SSE endpoints
for launching workflows and streaming real-time progress updates.

Port: 8050 (Discovery Agent uses 8100)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Path helpers (PyInstaller-aware)
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    _bundled_dir = os.path.join(sys._MEIPASS, "orchestrator_ui")
else:
    _bundled_dir = os.path.dirname(os.path.abspath(__file__))

_static_dir = os.path.join(_bundled_dir, "static")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global state for SSE streaming
# ---------------------------------------------------------------------------

class RunState:
    """Holds the current run's status and event queue for SSE clients."""

    def __init__(self):
        self.running = False
        self.cancel_requested = False
        self.events: list[dict] = []
        self._lock = threading.Lock()
        self._new_event = asyncio.Event()
        # Pause support
        self.pause_pending: dict | None = None   # {"title": ..., "message": ...}
        self.pause_resolved = threading.Event()
        # Track workflow for cancellation
        self._workflow_thread: threading.Thread | None = None
        self._workflow_loop: asyncio.AbstractEventLoop | None = None
        self._browser = None  # Playwright browser instance

    def reset(self):
        with self._lock:
            self.events.clear()
            self.running = False
            self.cancel_requested = False
            self.pause_pending = None
            self.pause_resolved.clear()
            self._browser = None
            self._workflow_loop = None

    def push_event(self, event_type: str, data: dict):
        with self._lock:
            self.events.append({"type": event_type, "data": data})
        # Wake up any SSE listeners
        try:
            self._new_event.set()
        except Exception:
            pass

    def get_events_since(self, cursor: int) -> list[dict]:
        with self._lock:
            return self.events[cursor:]

    def has_all_done(self) -> bool:
        """Check if all_done event was already pushed."""
        with self._lock:
            return any(e["type"] == "all_done" for e in self.events)


run_state = RunState()

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(title="Reporting Orchestrator UI")

# Mount the Discovery Agent app as a sub-application (same origin = no CORS issues)
try:
    from Workday_Report_Discovery_Agent.api_server import app as discovery_app
    from Workday_Report_Discovery_Agent import api_server as _disc_mod
    from Workday_Report_Discovery_Agent.agent import ReportDiscoveryAgent as _DiscAgent
    app.mount("/discovery", discovery_app)

    # Sub-app lifespans don't auto-fire in FastAPI mount, so initialize manually
    if _disc_mod.agent is None:
        logger.info("Initializing Discovery Agent manually for sub-app mount…")
        _disc_mod.agent = _DiscAgent()
        logger.info("Discovery Agent initialized with %d reports.", len(_disc_mod.agent.catalog))
    logger.info("Discovery Agent sub-app mounted at /discovery")
except Exception as exc:
    logger.warning("Could not mount Discovery Agent: %s", exc)

# Serve static files (CSS, JS)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class LaunchRequest(BaseModel):
    workflow: str  # "full" | "report_migration" | "dashboard_migration" | "export"
    industry: str | None = None
    items: list[str] = []
    run_export: bool = False
    wd_user: str = ""
    wd_pass: str = ""


class PauseResolve(BaseModel):
    pass  # Empty body — just signals "resume"


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve the main SPA page."""
    index_path = os.path.join(_static_dir, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/env-status")
def env_status():
    """Return which config values are set (for the config form)."""
    return {
        "openai_api_key": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
        "wd_user": bool(os.environ.get("WD_USER", "").strip()),
        "wd_pass": bool(os.environ.get("WD_PASS", "").strip()),
    }


# ---------------------------------------------------------------------------
# Discovery Agent management
# ---------------------------------------------------------------------------

# Discovery Agent is mounted as a sub-app at /discovery — no separate server needed.
# The start-discovery endpoint is kept for backward compatibility with the JS.


@app.post("/api/start-discovery")
def start_discovery():
    """Discovery Agent is auto-mounted as sub-app. This is a no-op."""
    return {"status": "ok"}


@app.get("/api/discovery-reports")
def get_discovery_reports():
    """Check if user has confirmed report selection in the Discovery UI."""
    try:
        from Workday_Report_Discovery_Agent.api_server import SELECTION_FILE
        if os.path.exists(SELECTION_FILE):
            import json as _json
            with open(SELECTION_FILE, "r", encoding="utf-8") as f:
                reports = _json.load(f)
            os.remove(SELECTION_FILE)
            return {"reports": reports}
    except Exception:
        pass
    return {"reports": []}


@app.get("/api/status")
def get_status():
    """Return current run status (poll fallback)."""
    return {
        "running": run_state.running,
        "event_count": len(run_state.events),
        "pause_pending": run_state.pause_pending,
    }


@app.get("/api/events")
async def sse_events(request: Request):
    """Server-Sent Events stream for real-time progress updates."""

    async def event_generator():
        cursor = 0
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            new_events = run_state.get_events_since(cursor)
            for evt in new_events:
                data = json.dumps(evt["data"])
                yield f"event: {evt['type']}\ndata: {data}\n\n"
                cursor += 1

                # If we sent "all_done", end the stream
                if evt["type"] == "all_done":
                    return

            # Wait for new events (with timeout to check disconnect)
            run_state._new_event.clear()
            try:
                await asyncio.wait_for(run_state._new_event.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                # Send keepalive comment
                yield ": keepalive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/launch")
async def launch_workflow(req: LaunchRequest):
    """Launch a workflow in a background thread."""
    if run_state.running:
        raise HTTPException(status_code=409, detail="A workflow is already running.")

    # Validate credentials — they're required for all workflows
    wd_user = req.wd_user or os.environ.get("WD_USER", "").strip()
    wd_pass = req.wd_pass or os.environ.get("WD_PASS", "")
    if not wd_user or not wd_pass:
        raise HTTPException(
            status_code=400,
            detail="Workday credentials are required. Please enter your username and password.",
        )

    run_state.reset()
    run_state.running = True

    # Set credentials in env (in-memory only, never persisted)
    os.environ["WD_USER"] = wd_user
    os.environ["WD_PASS"] = wd_pass

    # Launch in background thread (Playwright needs its own event loop)
    thread = threading.Thread(
        target=_run_workflow_thread,
        args=(req.workflow, req.industry, req.items, req.run_export),
        daemon=True,
        name="workflow-runner",
    )
    run_state._workflow_thread = thread
    thread.start()

    return {"status": "started", "workflow": req.workflow}


@app.post("/api/pause-resolve")
async def resolve_pause(body: PauseResolve):
    """Resume a paused workflow step (SSO login completed, etc.)."""
    if run_state.pause_pending:
        run_state.pause_resolved.set()
        run_state.pause_pending = None
        run_state.push_event("pause_resolved", {"message": "Resumed"})
        return {"status": "resumed"}
    raise HTTPException(status_code=400, detail="No pause pending")


@app.post("/api/cancel")
async def cancel_workflow():
    """Force-cancel the running workflow by closing the Playwright browser."""
    if not run_state.running:
        raise HTTPException(status_code=400, detail="No workflow is running.")

    run_state.cancel_requested = True
    # Unblock any paused step
    run_state.pause_resolved.set()

    # Force-close the Playwright browser — this kills all running automation
    browser = run_state._browser
    loop = run_state._workflow_loop
    if browser and loop and loop.is_running():
        try:
            future = asyncio.run_coroutine_threadsafe(browser.close(), loop)
            future.result(timeout=10)  # Wait up to 10s for browser to close
            logger.info("Playwright browser force-closed.")
        except Exception as exc:
            logger.warning("Failed to close browser: %s", exc)

    # The workflow thread's exception handler + cancel_check will immediately terminate the loop.
    # The thread will natively push agent_done and all_done events, so we do not push them here,
    # ensuring the frontend receives the full stream of cleanup events.
    run_state.push_event("error_event", {"message": "Workflow cancelled. Cleaning up..."})
    logger.info("Workflow cancellation requested by user.")
    return {"status": "cancelled"}


@app.post("/api/force-reset")
async def force_reset():
    """Force-reset the run state (escape hatch if a run gets stuck)."""
    run_state.reset()
    logger.info("Run state force-reset by user.")
    return {"status": "reset"}


# ---------------------------------------------------------------------------
# Background workflow runner
# ---------------------------------------------------------------------------

def _on_step(agent_name: str, step_num: int, total_steps: int, label: str, status: str = "done"):
    """Callback fired after each step — pushes SSE event."""
    run_state.push_event("step", {
        "agent": agent_name,
        "step": step_num,
        "total": total_steps,
        "label": label,
        "status": status,
    })


def _on_pause(title: str, message: str) -> None:
    """Callback for pause steps — blocks until web UI resolves it."""
    run_state.pause_pending = {"title": title, "message": message}
    run_state.pause_resolved.clear()
    run_state.push_event("pause", {"title": title, "message": message})
    # Block this thread until the UI sends POST /api/pause-resolve
    run_state.pause_resolved.wait(timeout=600)  # 10 min max wait


def _run_workflow_thread(workflow: str, industry: str | None, items: list[str], run_export_flag: bool):
    """Execute the workflow in a new asyncio event loop (runs in a background thread)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    run_state._workflow_loop = loop
    try:
        loop.run_until_complete(
            _run_workflow_async(workflow, industry, items, run_export_flag)
        )
    except Exception as exc:
        if run_state.cancel_requested:
            logger.info("Workflow thread terminated due to cancellation.")
        else:
            logger.error("Workflow error: %s", exc, exc_info=True)
            run_state.push_event("error_event", {"message": str(exc)})
    finally:
        # Always send all_done so the SSE client can close cleanly
        if not run_state.has_all_done():
            err_msg = "Task cancelled by user." if run_state.cancel_requested else "Workflow terminated unexpectedly."
            run_state.push_event("all_done", {
                "results": [{"agent": "System", "exit_code": 1, "error": err_msg, "elapsed": 0}],
                "package_name": None,
            })
        run_state.running = False
        run_state.cancel_requested = False
        run_state._browser = None
        run_state._workflow_loop = None
        loop.close()


async def _run_workflow_async(workflow: str, industry: str | None, items: list[str], run_export_flag: bool):
    """Core workflow executor — called from the background thread's event loop."""
    from playwright.async_api import async_playwright
    from run_agent import build_config as build_migration_config
    from run_dashboard_agent import build_config as build_dashboard_config
    from run_export import build_config as build_export_config
    from runner import run_config_async

    date_str = datetime.now().strftime("%m/%d/%Y")
    results = []
    package_name = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="chrome")
        run_state._browser = browser  # Store for cancel endpoint

        if workflow == "full":
            package_name = f"{industry}_Config_Package_{date_str}" if industry else None
            migration_config = build_migration_config(industry, items)

            async def _run_single_agent(name: str, config: dict, ctx):
                start_t = time.perf_counter()
                try:
                    exit_code, error = await run_config_async(
                        config, ctx, agent_name=name,
                        on_step=_on_step, on_pause=_on_pause,
                        cancel_check=lambda: run_state.cancel_requested,
                    )
                except Exception as exc:
                    exit_code, error = 1, str(exc)
                elapsed = time.perf_counter() - start_t
                entry = {
                    "agent": name,
                    "exit_code": exit_code,
                    "error": error,
                    "elapsed": round(elapsed, 1),
                }
                run_state.push_event("agent_done", entry)
                return entry

            coros = []

            # Migration agent (always)
            run_state.push_event("agent_start", {
                "agent": "Report Config Package",
                "total_steps": len(migration_config["steps"]),
            })
            ctx_migration = await browser.new_context(
                viewport={"width": 1440, "height": 900}, accept_downloads=True,
            )
            coros.append(_run_single_agent("Report Config Package", migration_config, ctx_migration))

            # Export agent (if toggled on) — runs in parallel
            ctx_export = None
            if run_export_flag:
                export_config = build_export_config(items)
                run_state.push_event("agent_start", {
                    "agent": "Export",
                    "total_steps": len(export_config["steps"]),
                })
                ctx_export = await browser.new_context(
                    viewport={"width": 1440, "height": 900}, accept_downloads=True,
                )
                coros.append(_run_single_agent("Export", export_config, ctx_export))

            # Run all agents in parallel via asyncio.gather
            gather_results = await asyncio.gather(*coros, return_exceptions=True)

            for res in gather_results:
                if isinstance(res, dict):
                    results.append(res)
                elif isinstance(res, Exception):
                    results.append({
                        "agent": "Unknown",
                        "exit_code": 1,
                        "error": str(res),
                        "elapsed": 0.0,
                    })

            try:
                await ctx_migration.close()
            except Exception:
                pass
            if ctx_export:
                try:
                    await ctx_export.close()
                except Exception:
                    pass

        elif workflow == "report_migration":
            package_name = f"{industry}_Config_Package_{date_str}" if industry else None
            migration_config = build_migration_config(industry, items)

            run_state.push_event("agent_start", {
                "agent": "Report Config Package",
                "total_steps": len(migration_config["steps"]),
            })
            ctx = await browser.new_context(
                viewport={"width": 1440, "height": 900}, accept_downloads=True,
            )
            start_t = time.perf_counter()
            exit_code, error = await run_config_async(
                migration_config, ctx, agent_name="Report Config Package",
                on_step=_on_step, on_pause=_on_pause,
                cancel_check=lambda: run_state.cancel_requested,
            )
            elapsed = time.perf_counter() - start_t
            results.append({
                "agent": "Report Config Package",
                "exit_code": exit_code,
                "error": error,
                "elapsed": round(elapsed, 1),
            })
            run_state.push_event("agent_done", results[-1])
            try:
                await ctx.close()
            except Exception:
                pass

        elif workflow == "dashboard_migration":
            package_name = f"{industry}_Dashboard_Config_Package_{date_str}" if industry else None
            dashboard_config = build_dashboard_config(industry, items)

            run_state.push_event("agent_start", {
                "agent": "Dashboard Config Package",
                "total_steps": len(dashboard_config["steps"]),
            })
            ctx = await browser.new_context(
                viewport={"width": 1440, "height": 900}, accept_downloads=True,
            )
            start_t = time.perf_counter()
            exit_code, error = await run_config_async(
                dashboard_config, ctx, agent_name="Dashboard Config Package",
                on_step=_on_step, on_pause=_on_pause,
                cancel_check=lambda: run_state.cancel_requested,
            )
            elapsed = time.perf_counter() - start_t
            results.append({
                "agent": "Dashboard Config Package",
                "exit_code": exit_code,
                "error": error,
                "elapsed": round(elapsed, 1),
            })
            run_state.push_event("agent_done", results[-1])
            try:
                await ctx.close()
            except Exception:
                pass

        elif workflow == "export":
            export_config = build_export_config(items)

            run_state.push_event("agent_start", {
                "agent": "Export",
                "total_steps": len(export_config["steps"]),
            })
            ctx = await browser.new_context(
                viewport={"width": 1440, "height": 900}, accept_downloads=True,
            )
            start_t = time.perf_counter()
            exit_code, error = await run_config_async(
                export_config, ctx, agent_name="Export",
                on_step=_on_step, on_pause=_on_pause,
                cancel_check=lambda: run_state.cancel_requested,
            )
            elapsed = time.perf_counter() - start_t
            results.append({
                "agent": "Export",
                "exit_code": exit_code,
                "error": error,
                "elapsed": round(elapsed, 1),
            })
            run_state.push_event("agent_done", results[-1])
            try:
                await ctx.close()
            except Exception:
                pass

        try:
            await browser.close()
        except Exception:
            pass

    run_state.push_event("all_done", {
        "results": results,
        "package_name": package_name,
    })


# ---------------------------------------------------------------------------
# Server startup
# ---------------------------------------------------------------------------

def _free_port(port: int) -> None:
    """If port is occupied, kill the process listening on it to prevent [Errno 10048]."""
    import socket
    import subprocess
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", port)) == 0:
            logger.info("Port %d is already in use. Terminating old server instance...", port)
            try:
                if sys.platform == "win32":
                    output = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True).decode()
                    pids = set()
                    for line in output.strip().splitlines():
                        if f":{port}" in line and "LISTENING" in line:
                            parts = line.strip().split()
                            if parts:
                                pids.add(parts[-1])
                    for pid in pids:
                        if pid and pid != "0" and int(pid) != os.getpid():
                            subprocess.call(f"taskkill /F /PID {pid}", shell=True)
                    time.sleep(1)
            except Exception as exc:
                logger.warning("Could not automatically free port %d: %s", port, exc)


def start_orchestrator_server(port: int = 8050):
    """Start the FastAPI server and open the browser."""
    import uvicorn
    import webbrowser

    _free_port(port)

    url = f"http://127.0.0.1:{port}"
    logger.info("Starting Orchestrator Web UI on %s", url)

    # Open browser after a short delay
    def _open_browser():
        time.sleep(2)
        webbrowser.open(url)

    threading.Thread(target=_open_browser, daemon=True).start()

    # Run the server (blocks)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
