# Shutdown Feature Documentation

## Overview
The system now includes automatic process cleanup and a dashboard shutdown button to prevent stale processes from blocking updates.

## Features

### 1. Automatic Process Cleanup (Windows)
When you run `run_forwarder.bat`, it now:
- **Automatically kills** any existing processes before starting:
  - `mention_bot.py`
  - `message_forwarder.py`
  - `d2d.py`
  - `http_server.py` (or `python -m http.server`)

This ensures you always get a fresh start with the latest code.

### 2. Automatic Process Cleanup (Linux/Mac)
When you run `run.sh`, it now:
- **Automatically kills** any existing processes before starting:
  - `mention_bot.py`
  - `message_forwarder.py`
  - `d2d.py`
  - `http_server.py` (or `python -m http.server`)
  - Waits 1 second to ensure cleanup completes

### 3. Dashboard Shutdown Button
The dashboard now has a **⏻ Shutdown** button in the top-right corner that:
- Shows a confirmation dialog
- Calls the `/shutdown` endpoint
- Gracefully stops the HTTP server
- Displays a success message
- Auto-closes the dashboard after 5 seconds

## Usage

### Normal Operation
1. Run `run_forwarder.bat` (Windows) or `run.sh` (Linux/Mac)
2. System automatically kills any old processes
3. Fresh instances start up
4. Dashboard loads with latest code

### Manual Shutdown via Dashboard
1. Click the **⏻ Shutdown** button in the dashboard
2. Confirm the shutdown
3. System stops all processes and closes

### Force Clean Restart
If you need to force everything to stop:
- **Windows**: Just run `run_forwarder.bat` again (it will auto-kill everything)
- **Linux/Mac**: Run `run.sh` again

## Technical Details

### New Files
- `http_server.py` - Custom HTTP server with `/shutdown` endpoint

### Modified Files
- `run_forwarder.bat` - Now kills old processes before starting
- `run.sh` - Now kills old processes before starting
- `dashboard.html` - Added shutdown button and JavaScript function

## Troubleshooting

### Dashboard Shows Old Content
**Solution**: Click the **⏻ Shutdown** button, wait 5 seconds, then run the startup script again.

### Port 8080 Still in Use
**Solution**: The startup scripts now automatically kill the old HTTP server, but if issues persist:
```bash
# On Linux/Mac
pkill -f http_server.py
pkill -f "python -m http.server"

# On Windows (in PowerShell)
Get-Process python | Where-Object {$_.Path -like "*http*"} | Stop-Process -Force
```

### Python Processes Keep Running
**Solution**: The startup scripts now automatically kill all related Python processes before starting.

## Benefits
✅ No more stale processes blocking updates  
✅ Clean shutdown from the dashboard  
✅ Automatic cleanup on every start  
✅ Always get the latest code and UI changes  
✅ One-click shutdown button
