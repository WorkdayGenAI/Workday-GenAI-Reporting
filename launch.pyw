"""No-console launcher for the Workday Report Orchestrator.

Run this with pythonw.exe (or double-click the .pyw file) to start the
web UI without showing a terminal window.  The browser opens automatically.

    pythonw.exe launch.pyw

For development / debugging, use orchestrator.py directly instead — it
shows the full console log.
"""

import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Suppress all console output (no terminal to write to)
if not sys.stdout or not hasattr(sys.stdout, "write"):
    sys.stdout = open(os.devnull, "w")
if not sys.stderr or not hasattr(sys.stderr, "write"):
    sys.stderr = open(os.devnull, "w")

# Boot essentials
from utils import ensure_env_file, ensure_playwright_installed
ensure_env_file()
ensure_playwright_installed()

# Launch the web server (it opens the browser automatically)
from orchestrator_ui.server import start_orchestrator_server
start_orchestrator_server(port=8050)
