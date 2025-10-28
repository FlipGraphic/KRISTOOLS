@echo off
setlocal enableextensions enabledelayedexpansion

rem Anchor to repo root
cd /d "%~dp0\..\.."

rem Activate shared virtualenv
call "%CD%\env_setup.bat"

set D2D_DIR=%CD%\Discord2Discord
set LOGS_DIR=%D2D_DIR%\logs
set PYTHONUNBUFFERED=1
set PYTHONPATH=%D2D_DIR%

if not exist "%LOGS_DIR%" (
  mkdir "%LOGS_DIR%"
)

REM Clean up stale lock file (if exists)
if exist "%D2D_DIR%\.d2d.lock" (
  echo Removing stale .d2d.lock file...
  del "%D2D_DIR%\.d2d.lock" 2>nul
)

set /p CLEARLOGS=Clear existing Discord2Discord logs before startup? [Y/N]: 
if /I "%CLEARLOGS%"=="Y" (
  for %%F in ("%LOGS_DIR%\*.json") do (
    >"%%F" echo [{"timestamp":"%date% %time%","level":"INFO","event":"Logs reset successfully"}]
  )
)

echo Launching Discord2Discord bots and HTTP server (logs visible)...
start "D2D - mention_bot" cmd /k "cd /d "%D2D_DIR%" && set PYTHONPATH=%PYTHONPATH% && python src\bots\mention_bot.py"
start "D2D - message_forwarder" cmd /k "cd /d "%D2D_DIR%" && set PYTHONPATH=%PYTHONPATH% && python src\bots\message_forwarder.py"
start "D2D - d2d" cmd /k "cd /d "%D2D_DIR%" && set PYTHONPATH=%PYTHONPATH% && python src\bots\d2d.py"
start "D2D - HTTP 8080" cmd /k "cd /d "%D2D_DIR%\src\web" && set PYTHONPATH=%PYTHONPATH% && python http_server.py 8080"

echo Open dashboard at: http://localhost:8080/dashboard.html
endlocal
exit /b 0
