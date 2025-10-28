@echo off
setlocal enableextensions enabledelayedexpansion

set ROOT_DIR=%~dp0

if not exist "%ROOT_DIR%\.venv" (
  py -3 -m venv "%ROOT_DIR%\.venv"
)
call "%ROOT_DIR%\.venv\Scripts\activate.bat"

python -m pip install --upgrade pip
pip install -r "%ROOT_DIR%\requirements.txt"

start "PAAPI" /MIN cmd /c "set PYTHONUNBUFFERED=1 && python "%ROOT_DIR%\src\amz_api_tool.py""
start "DASH"  /MIN cmd /c "set PYTHONUNBUFFERED=1 && python "%ROOT_DIR%\src\server.py""

echo.
echo Servers starting...
echo - Amazon:   http://127.0.0.1:5050/health
echo - Dashboard: http://127.0.0.1:8000/web/Daily.html

echo Waiting 3 seconds for server to start...
timeout /t 3 /nobreak >nul

echo Opening Daily.html in Chrome Profile 3...

:: Try to find Chrome in common locations
set CHROME_PATH=""
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set CHROME_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set CHROME_PATH="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
) else if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set CHROME_PATH="%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
)

if not "%CHROME_PATH%"=="" (
    start "" %CHROME_PATH% --profile-directory="Profile 3" "http://127.0.0.1:8000/web/Daily.html"
) else (
    echo Chrome not found, please manually open: http://127.0.0.1:8000/web/Daily.html
)

echo Press any key to stop (this will close only this window).
pause >nul
endlocal
