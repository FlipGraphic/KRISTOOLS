#!/usr/bin/env python3
"""
Discord Bot Shutdown Script
Properly stops all Discord bot processes
"""

import subprocess
import sys
import os
import signal
import time

def kill_python_processes():
    """Kill all Python processes related to Discord bots"""
    print("[SHUTDOWN] Stopping Discord bot processes...")
    
    try:
        # On Windows
        if os.name == 'nt':
            # Kill all Python processes
            result = subprocess.run(['taskkill', '/F', '/IM', 'python.exe'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print("[SHUTDOWN] All Python processes stopped")
            else:
                print(f"[SHUTDOWN] Some processes may not have stopped: {result.stderr}")
        else:
            # On Linux/Mac
            subprocess.run(['pkill', '-f', 'd2d.py'], check=False)
            subprocess.run(['pkill', '-f', 'message_forwarder.py'], check=False)
            subprocess.run(['pkill', '-f', 'mention_bot.py'], check=False)
            subprocess.run(['pkill', '-f', 'http_server.py'], check=False)
            print("[SHUTDOWN] All Discord bot processes stopped")
            
    except Exception as e:
        print(f"[SHUTDOWN] Error stopping processes: {e}")

def kill_http_server():
    """Kill HTTP server on port 8080"""
    print("[SHUTDOWN] Stopping HTTP server...")
    
    try:
        if os.name == 'nt':
            # Windows - kill processes using port 8080
            result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if ':8080' in line and 'LISTENING' in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        subprocess.run(['taskkill', '/F', '/PID', pid], check=False)
                        print(f"[SHUTDOWN] HTTP server (PID {pid}) stopped")
        else:
            # Linux/Mac
            subprocess.run(['lsof', '-ti:8080'], check=False)
            subprocess.run(['pkill', '-f', 'http.server'], check=False)
            print("[SHUTDOWN] HTTP server stopped")
            
    except Exception as e:
        print(f"[SHUTDOWN] HTTP server may already be stopped: {e}")

def main():
    print("=" * 60)
    print("DISCORD BOT SHUTDOWN")
    print("=" * 60)
    
    # Stop all processes
    kill_python_processes()
    kill_http_server()
    
    # Wait a moment for cleanup
    time.sleep(2)
    
    print("\n" + "=" * 60)
    print("SHUTDOWN COMPLETE")
    print("=" * 60)
    print("All Discord bot processes have been stopped.")
    print("You can now safely restart the system.")
    print("=" * 60)

if __name__ == "__main__":
    main()
