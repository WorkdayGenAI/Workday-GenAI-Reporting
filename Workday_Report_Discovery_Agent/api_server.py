import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if getattr(sys, 'frozen', False):
    _user_dir = os.path.dirname(sys.executable)
    _bundled_dir = sys._MEIPASS
else:
    _user_dir = os.path.dirname(os.path.abspath(__file__))
    _bundled_dir = os.path.dirname(os.path.abspath(__file__))

import json
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from agent import ReportDiscoveryAgent
from sync_catalog import sync_from_workday

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# App lifecycle (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------

agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise the agent on startup."""
    global agent
    logger.info("Initializing ReportDiscoveryAgent...")
    agent = ReportDiscoveryAgent()
    logger.info("Agent initialized successfully.")
    yield


# Initialize FastAPI app
app = FastAPI(title="Report Discovery Agent API", lifespan=lifespan)


# ---------------------------------------------------------------------------
# API Models
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str
    bm25_top_n: int = 50
    llm_top_k: int = 20
    use_llm: bool = True


class ConfirmRequest(BaseModel):
    reports: list[str]


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/search")
def search_reports(req: SearchRequest):
    global agent
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    try:
        if req.use_llm:
            results = agent.search(
                query=req.query,
                bm25_top_n=req.bm25_top_n,
                llm_top_k=req.llm_top_k
            )
        else:
            results = agent.search_bm25_only(
                query=req.query,
                top_n=req.llm_top_k
            )
        return {"results": results}
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sync")
def sync_reports():
    global agent
    try:
        success = sync_from_workday()
        if not success:
            raise HTTPException(status_code=500, detail="Sync failed. Check credentials or Workday RaaS URL.")

        # Reload agent to pick up new catalog
        logger.info("Reloading agent with new catalog...")
        agent = ReportDiscoveryAgent()

        return {"success": True, "message": f"Successfully synced and loaded {len(agent.catalog)} reports."}
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
def get_stats():
    global agent
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    num_reports = len(agent.catalog)
    return {
        "num_reports": num_reports,
        "llm_enabled": bool(config.OPENAI_API_KEY),
        "llm_model": config.MODEL_NAME
    }


# ---------------------------------------------------------------------------
# Orchestrator Integration (Selection & Confirmation)
# ---------------------------------------------------------------------------

SELECTION_FILE = os.path.join(_user_dir, ".selected_reports.json")
_confirmation_event = threading.Event()


@app.post("/api/confirm")
def confirm_selection(req: ConfirmRequest):
    """Called by the frontend when the user clicks 'Proceed with Selected Reports'."""
    if not req.reports:
        raise HTTPException(status_code=400, detail="No reports selected")

    # Write the selection to disk for the orchestrator to read.
    with open(SELECTION_FILE, "w", encoding="utf-8") as f:
        json.dump(req.reports, f)

    logger.info("User confirmed %d reports: %s", len(req.reports), req.reports)

    # Signal the orchestrator that the user has confirmed.
    _confirmation_event.set()

    return {"success": True, "message": f"{len(req.reports)} reports selected. You can close this tab."}


# ---------------------------------------------------------------------------
# Static files (must be mounted AFTER all API routes)
# ---------------------------------------------------------------------------

static_dir = os.path.join(_bundled_dir, "static")
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


# ---------------------------------------------------------------------------
# Helpers for orchestrator integration
# ---------------------------------------------------------------------------

def wait_for_confirmation(timeout: float = 600) -> list[str]:
    """Block until the user confirms their selection in the web UI.

    Returns the list of selected report names, or an empty list on timeout.
    """
    logger.info("Waiting for user to select reports in the web UI (timeout: %.0fs)…", timeout)
    confirmed = _confirmation_event.wait(timeout=timeout)
    _confirmation_event.clear()

    if not confirmed:
        logger.warning("Timed out waiting for report selection.")
        return []

    try:
        with open(SELECTION_FILE, "r", encoding="utf-8") as f:
            reports = json.load(f)
        os.remove(SELECTION_FILE)  # Clean up
        return reports
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def start_server(port: int = 8000) -> threading.Thread:
    """Start the FastAPI server in a background thread. Returns the thread."""
    import uvicorn
    import time

    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(cfg)

    thread = threading.Thread(target=server.run, daemon=True, name="discovery-server")
    thread.start()

    # Give the server a moment to start
    time.sleep(2)

    return thread


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
