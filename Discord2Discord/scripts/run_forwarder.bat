@echo off
setlocal enableextensions enabledelayedexpansion
cd /d "%~dp0\.."

:: Kill any existing HTTP servers on port 8080
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8080.*LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

:: Hide console window for cleaner experience
if not "%1"=="min" (
    start /min "" "%~nx0" min
    exit
)

:: Load environment from tokenkeys.env if present, else .env (simple parser)
if exist config\tokenkeys.env (
  for /f "usebackq tokens=* delims=" %%a in ("config\tokenkeys.env") do (
    for /f "tokens=1,2 delims==" %%i in ("%%a") do (
      if not "%%i"=="" (
        set "%%i=%%j"
      )
    )
  )
) else if exist config\.env (
  for /f "usebackq tokens=* delims=" %%a in ("config\.env") do (
    for /f "tokens=1,2 delims==" %%i in ("%%a") do (
      if not "%%i"=="" (
        set "%%i=%%j"
      )
    )
  )
)

:: Start bots completely hidden (no windows at all)
start /b python src/bots/mention_bot.py >nul 2>&1
start /b python src/bots/message_forwarder.py >nul 2>&1

:: Wait a moment for bots to start, then start HTTP server and open dashboard
timeout /t 3 /nobreak >nul

:: Start HTTP server from project root and serve dashboard.html
::: Use our custom server with shutdown endpoint
start /min "HTTP Server" cmd /c "cd /d src\web && python http_server.py 8080 >nul 2>&1"

:: Wait for server to be ready, then open dashboard with specific Chrome profile
timeout /t 4 /nobreak >nul

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
    start "" %CHROME_PATH% --profile-directory="Profile 3" --new-window http://localhost:8080/dashboard.html
) else (
    echo Chrome not found, please manually open: http://localhost:8080/dashboard.html
)

:: Hide this window and run bridge in background
start /b python src/bots/d2d.py >nul 2>&1
exit
