@echo off
REM ── Launch the Workday Report Orchestrator (no console window) ──
REM This batch file starts the web UI silently. The browser opens automatically.

REM Try the venv first, then fall back to system python
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" launch.pyw
) else (
    start "" pythonw launch.pyw
)
