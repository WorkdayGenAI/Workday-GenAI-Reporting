@echo off
echo Installing requirements...
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

echo.
echo Building standalone executable with PyInstaller...
.\.venv\Scripts\pyinstaller.exe --noconfirm ^
    --onefile ^
    --name "Reporting_Orchestrator" ^
    --add-data "Workday_Report_Discovery_Agent/static;Workday_Report_Discovery_Agent/static" ^
    --add-data "Workday_Report_Discovery_Agent/data;Workday_Report_Discovery_Agent/data" ^
    --add-data "Workday_Report_Discovery_Agent/prompts;Workday_Report_Discovery_Agent/prompts" ^
    --add-data "orchestrator_ui/static;orchestrator_ui/static" ^
    --hidden-import "Workday_Report_Discovery_Agent" ^
    --hidden-import "Workday_Report_Discovery_Agent.config" ^
    --hidden-import "Workday_Report_Discovery_Agent.api_server" ^
    --hidden-import "Workday_Report_Discovery_Agent.agent" ^
    --hidden-import "Workday_Report_Discovery_Agent.bm25_engine" ^
    --hidden-import "Workday_Report_Discovery_Agent.llm_scorer" ^
    --hidden-import "Workday_Report_Discovery_Agent.report_catalog" ^
    --hidden-import "Workday_Report_Discovery_Agent.stemmer" ^
    --hidden-import "Workday_Report_Discovery_Agent.synonyms" ^
    --hidden-import "Workday_Report_Discovery_Agent.sync_catalog" ^
    --hidden-import "Workday_Report_Discovery_Agent.cli" ^
    --hidden-import "orchestrator_ui" ^
    --hidden-import "orchestrator_ui.server" ^
    --hidden-import "uvicorn.logging" ^
    --hidden-import "uvicorn.loops" ^
    --hidden-import "uvicorn.loops.auto" ^
    --hidden-import "uvicorn.protocols" ^
    --hidden-import "uvicorn.protocols.http" ^
    --hidden-import "uvicorn.protocols.http.auto" ^
    --hidden-import "uvicorn.protocols.websockets" ^
    --hidden-import "uvicorn.protocols.websockets.auto" ^
    --hidden-import "uvicorn.lifespan" ^
    --hidden-import "uvicorn.lifespan.on" ^
    orchestrator.py

echo.
echo Build complete. Executable is located in dist\Reporting_Orchestrator.exe
