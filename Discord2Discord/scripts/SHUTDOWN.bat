@echo off
echo ================================================
echo           DISCORD BOT SHUTDOWN
echo ================================================
echo.
echo Stopping all Discord bot processes...
echo.

REM Kill all Python processes
taskkill /F /IM python.exe 2>nul
if %errorlevel% equ 0 (
    echo [OK] All Python processes stopped
) else (
    echo [INFO] No Python processes found
)

REM Kill HTTP server on port 8080
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8080 ^| findstr LISTENING') do (
    taskkill /F /PID %%a 2>nul
    echo [OK] HTTP server stopped (PID %%a)
)

echo.
echo ================================================
echo           SHUTDOWN COMPLETE
echo ================================================
echo All Discord bot processes have been stopped.
echo You can now safely restart the system.
echo ================================================
echo.
echo Press any key to exit...
pause >nul