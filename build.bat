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
    orchestrator.py

echo.
echo Build complete. Executable is located in dist\Reporting_Orchestrator.exe
pause
