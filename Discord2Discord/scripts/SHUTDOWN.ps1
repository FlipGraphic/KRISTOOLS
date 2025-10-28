# Discord Bot Shutdown Script (PowerShell)
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "          DISCORD BOT SHUTDOWN" -ForegroundColor Cyan  
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Stopping all Discord bot processes..." -ForegroundColor Yellow
Write-Host ""

# Kill all Python processes
$pythonProcesses = Get-Process python -ErrorAction SilentlyContinue
if ($pythonProcesses) {
    $pythonProcesses | Stop-Process -Force
    Write-Host "[OK] All Python processes stopped" -ForegroundColor Green
} else {
    Write-Host "[INFO] No Python processes found" -ForegroundColor Blue
}

# Kill HTTP server on port 8080
$port8080Processes = Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
if ($port8080Processes) {
    foreach ($pid in $port8080Processes) {
        try {
            Stop-Process -Id $pid -Force
            Write-Host "[OK] HTTP server stopped (PID $pid)" -ForegroundColor Green
        } catch {
            Write-Host "[WARN] Could not stop process $pid" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "[INFO] No processes found on port 8080" -ForegroundColor Blue
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "          SHUTDOWN COMPLETE" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "All Discord bot processes have been stopped." -ForegroundColor White
Write-Host "You can now safely restart the system." -ForegroundColor White
Write-Host "================================================" -ForegroundColor Cyan

Read-Host "Press Enter to exit"
