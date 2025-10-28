#!/usr/bin/env python3
"""Silent Launcher for Discord2Discord Bridge - Runs without terminal window"""
import subprocess
import sys
import os
import time
from datetime import datetime

try:
    # Pull feature flags from config (loads tokenkeys.env)
    from src.core.config import (
        _str_to_bool as _cfg_bool,  # type: ignore
    )
except Exception:
    def _cfg_bool(v, d=False):
        return str(v).strip().lower() in {"1","true","yes","on"} if v is not None else d


def clear_logs() -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logs_dir = os.path.join(project_root, 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    # Known log files; create/reset if present
    candidate_logs = [
        'botlogs.json',
        'd2dlogs.json',
        'filteredlogs.json',
        'backend_status.json',
        'dashboardlogs.json',
        'systemlogs.json',
    ]
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    reset_payload = f'[{"timestamp":"{timestamp}","level":"INFO","event":"Logs reset successfully"}]'

    for log_name in candidate_logs:
        log_path = os.path.join(logs_dir, log_name)
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(reset_payload)
        except Exception:
            # Ignore errors if file cannot be created; proceed to next
            pass

    print("[LAUNCHER] Logs reset in", logs_dir)


def main():
    # Change to script directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Handle --clearlogs CLI
    if any(arg == '--clearlogs' for arg in sys.argv[1:]):
        clear_logs()
        return
    
    # Start all processes as detached
    processes = []
    
    print("[LAUNCHER] Starting bots...")
    
    # Feature flags (default: all enabled)
    enable_d2d = _cfg_bool(os.getenv('ENABLE_D2D', 'true'), True)
    enable_forwarder = _cfg_bool(os.getenv('ENABLE_FORWARDER', 'true'), True)
    enable_mention = _cfg_bool(os.getenv('ENABLE_MENTION_BOT', 'true'), True)

    # Determine which scripts to launch
    launch_list = []
    if enable_mention:
        launch_list.append('src/bots/mention_bot.py')
    if enable_forwarder:
        launch_list.append('src/bots/message_forwarder.py')
    if enable_d2d:
        launch_list.append('src/bots/d2d.py')

    # Start selected processes (no legacy console_*.log files)
    for bot in launch_list:
        if os.path.exists(bot):
            proc = subprocess.Popen(
                [sys.executable, bot],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                bufsize=0,  # Unbuffered
                universal_newlines=True
            )
            processes.append(proc)
            print(f"[LAUNCHER] Started {bot}")
    
    # Wait a moment
    time.sleep(3)
    
    # Start HTTP server (serve static files from src/web by setting cwd)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    web_cwd = os.path.join(project_root, 'src', 'web')
    http_proc = subprocess.Popen(
        [sys.executable, 'http_server.py', '8080'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
        bufsize=0,  # Unbuffered
        universal_newlines=True,
        cwd=web_cwd,
    )
    print("[LAUNCHER] Started HTTP server")
    
    # Wait for server to be ready and verify it's running
    print("[LAUNCHER] Waiting for HTTP server to be ready...")
    import requests
    max_retries = 10
    for i in range(max_retries):
        try:
            response = requests.get('http://localhost:8080/status', timeout=2)
            if response.status_code == 200:
                print("[LAUNCHER] HTTP server is ready!")
                break
        except Exception:
            pass
        time.sleep(1)
        print(f"[LAUNCHER] Retry {i+1}/{max_retries}...")
    else:
        print("[LAUNCHER] Warning: Could not verify HTTP server is ready")
    
    # Open browser
    chrome_paths = [
        r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        r"C:\\Users\\{}\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe".format(os.getenv('USERNAME', '')),
    ]
    
    chrome_path = None
    for path in chrome_paths:
        if os.path.exists(path):
            chrome_path = path
            break
    
    if chrome_path:
        dashboard_url = 'http://localhost:8080/dashboard.html'
        print(f"[LAUNCHER] Opening dashboard: {dashboard_url}")
        subprocess.Popen([
            chrome_path,
            '--profile-directory=Profile 3',
            '--new-window',
            dashboard_url
        ], creationflags=subprocess.CREATE_NO_WINDOW)
        print("[LAUNCHER] Opened dashboard in Chrome")
    else:
        print("[LAUNCHER] Chrome not found, please manually open: http://localhost:8080/dashboard.html")
    
    print("[LAUNCHER] All services started")

if __name__ == '__main__':
    main()
