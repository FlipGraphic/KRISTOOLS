@echo off
setlocal enableextensions enabledelayedexpansion

rem Anchor to repo root
cd /d "%~dp0\..\.."

rem Activate shared virtualenv
call "%CD%\env_setup.bat"

set RS_DIR=%CD%\RS-Agenda-Tool
set PYTHONUNBUFFERED=1

rem (Optional) RS-Agenda doesn't maintain JSON logs by default; skip clear prompt.
echo Launching RS-Agenda servers (logs visible)...
start "RS-Agenda - API (5050)" cmd /k "cd /d "%RS_DIR%" && python src\amz_api_tool.py"
start "RS-Agenda - Server (8000)" cmd /k "cd /d "%RS_DIR%" && python src\server.py"

echo Open dashboard at: http://127.0.0.1:8000/web/Daily.html
endlocal
exit /b 0
