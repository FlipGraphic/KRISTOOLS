#!/usr/bin/env python3
"""Working HTTP Server for Dashboard with all endpoints functioning"""
import http.server
import socketserver
import signal
import sys
import os
import json
import urllib.parse
import requests

# Load config for tokens and channel map
try:
    from src.core.config import DISCORD_TOKEN, SOURCE_GUILD_ID, MENTION_BOT_TOKEN, DESTINATION_GUILD_ID, load_channel_map
    from src.core.log_utils import write_enhanced_log
except Exception:
    DISCORD_TOKEN = ""
    SOURCE_GUILD_ID = ""
    def load_channel_map(path: str = None):
        try:
            root = os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(root, 'channel_map.json'), 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    def write_enhanced_log(**kwargs):
        pass
    MENTION_BOT_TOKEN = ""
    DESTINATION_GUILD_ID = ""

class WorkingHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        print(f"[HTTP] POST request to: {self.path}")
        if self.path == '/shutdown':
            try:
                # Acknowledge first, then exit shortly after
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'shutdown_initiated'}).encode('utf-8'))
                import threading
                import subprocess
                def delayed_shutdown():
                    import time
                    time.sleep(1)
                    print("[SHUTDOWN] Received shutdown request from dashboard (POST)")
                    try:
                        if os.name == 'nt':
                            # Aggressively terminate python and cmd process trees
                            cmds = [
                                ['taskkill', '/F', '/IM', 'python.exe', '/T'],
                                ['taskkill', '/F', '/IM', 'pythonw.exe', '/T'],
                                ['taskkill', '/F', '/IM', 'cmd.exe', '/T'],
                            ]
                            for cmd in cmds:
                                try:
                                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                except Exception:
                                    pass
                        else:
                            os._exit(0)
                    except Exception:
                        pass
                    finally:
                        # Ensure current server exits if still alive
                        try:
                            os._exit(0)
                        except Exception:
                            pass
                threading.Thread(target=delayed_shutdown, daemon=True).start()
            except Exception as e:
                self.send_response(500)
                self.end_headers()
            return

        if self.path.startswith('/save_channel_map'):
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                print(f"[HTTP] Content-Length: {content_length}")
                
                if content_length > 0:
                    post_data = self.rfile.read(content_length)
                    print(f"[HTTP] Post data: {post_data}")
                    
                    channel_map_data = json.loads(post_data.decode('utf-8'))
                    print(f"[HTTP] Parsed JSON: {channel_map_data}")
                    
                    # Save to file
                    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    channel_map_path = os.path.join(root, 'config', 'channel_map.json')
                    with open(channel_map_path, 'w', encoding='utf-8-sig') as f:
                        json.dump(channel_map_data, f, indent=2, ensure_ascii=False)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': True}).encode('utf-8'))
                    print(f"[HTTP] Success response sent")
                else:
                    self.send_response(400)
                    self.end_headers()
                    print(f"[HTTP] Bad request - no content")
            except Exception as e:
                print(f"[HTTP] Exception: {e}")
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()
            print(f"[HTTP] Unknown POST path: {self.path}")

    def do_GET(self):
        if self.path.startswith('/status'):
            try:
                root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                map_path = os.path.join(root, 'config', 'channel_map.json')

                map_exists = os.path.exists(map_path)

                map_len = 0
                if map_exists:
                    try:
                        # Use utf-8-sig to be tolerant of BOM and prior saves
                        with open(map_path, 'r', encoding='utf-8-sig') as f:
                            map_data = json.load(f)
                        map_len = len(map_data) if isinstance(map_data, dict) else 0
                    except Exception:
                        # Fallback read without BOM handling
                        try:
                            with open(map_path, 'r', encoding='utf-8') as f:
                                map_data = json.load(f)
                            map_len = len(map_data) if isinstance(map_data, dict) else 0
                        except Exception:
                            map_len = 0

                # Aggregate JSON-based logs information
                log_files = [
                    os.path.join(root, 'logs', 'filteredlogs.json'),
                    os.path.join(root, 'logs', 'd2dlogs.json'),
                    os.path.join(root, 'logs', 'botlogs.json'),
                ]
                logs_count = 0
                latest_ts = None
                for lf in log_files:
                    if os.path.exists(lf):
                        try:
                            with open(lf, 'r', encoding='utf-8') as f:
                                items = json.load(f)
                                if isinstance(items, list):
                                    logs_count += len(items)
                                    # Find newest timestamp string
                                    for it in items:
                                        ts = it.get('timestamp')
                                        if ts:
                                            if latest_ts is None or str(ts) > str(latest_ts):
                                                latest_ts = ts
                        except Exception:
                            pass

                status_data = {
                    'channel_map_exists': map_exists,
                    'channel_map_count': map_len,
                    'server_status': 'running',
                    'logs_exists': logs_count > 0,
                    'logs_count': logs_count,
                    'latest_log_timestamp': latest_ts,
                }

                payload = json.dumps(status_data, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                return

        # Legacy console logs endpoint removed; logs are now served via JSON files

        elif self.path.startswith('/filteredlogs.json') or self.path.startswith('/d2dlogs.json') or self.path.startswith('/botlogs.json'):
            try:
                root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                
                # Determine which log file to serve
                if self.path.startswith('/filteredlogs.json'):
                    logs_path = os.path.join(root, 'logs', 'filteredlogs.json')
                    log_type = 'filteredlogs'
                elif self.path.startswith('/d2dlogs.json'):
                    logs_path = os.path.join(root, 'logs', 'd2dlogs.json')
                    log_type = 'd2dlogs'
                elif self.path.startswith('/botlogs.json'):
                    logs_path = os.path.join(root, 'logs', 'botlogs.json')
                    log_type = 'botlogs'
                else:
                    # This should not happen with current paths
                    self.send_response(404)
                    self.end_headers()
                    return
                
                if os.path.exists(logs_path):
                    with open(logs_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    payload = json.dumps({
                        'logs': json.loads(content),
                        'log_type': log_type,
                        'success': True
                    }, ensure_ascii=False).encode('utf-8')
                    
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                    self.send_header('Content-Length', str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                else:
                    payload = json.dumps({
                        'logs': [],
                        'log_type': log_type,
                        'success': False,
                        'error': f'{log_type} logs not found'
                    }, ensure_ascii=False).encode('utf-8')
                    
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                    self.send_header('Content-Length', str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                return
            except Exception as e:
                payload = json.dumps({
                    'logs': [],
                    'success': False,
                    'error': str(e)
                }, ensure_ascii=False).encode('utf-8')
                
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

        elif self.path.startswith('/channel_map.json'):
            try:
                root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                map_path = os.path.join(root, 'config', 'channel_map.json')
                data = {}
                if os.path.exists(map_path):
                    try:
                        with open(map_path, 'r', encoding='utf-8-sig') as f:
                            data = json.load(f)
                    except Exception:
                        with open(map_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                payload = json.dumps(data or {}, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            except Exception:
                self.send_response(500)
                self.end_headers()
                return

        # removed: shutdown handling from GET; now handled in POST

        elif self.path.startswith('/pull_channels'):
            try:
                # Parse query parameters
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                src_server = params.get('src', [''])[0]
                dest_server = params.get('dest', [''])[0]
                
                # Phase 1: Placeholder implementation (returns mock count)
                # Phase 2: Will integrate Discord API to fetch channels
                count = len(src_server) + len(dest_server) if src_server and dest_server else 0
                
                response = {
                    'success': True,
                    'count': count,
                    'message': f'Pull channels from {src_server} to {dest_server} (placeholder)',
                    'note': 'Phase 1: Mock implementation. Phase 2 will integrate Discord API.'
                }
                
                payload = json.dumps(response, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            except Exception as e:
                payload = json.dumps({
                    'success': False,
                    'error': str(e)
                }, ensure_ascii=False).encode('utf-8')
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

        elif self.path.startswith('/channels_meta'):
            try:
                root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                map_path = os.path.join(root, 'config', 'channel_map.json')

                # Load map (tolerant of BOM)
                channel_map = {}
                if os.path.exists(map_path):
                    try:
                        with open(map_path, 'r', encoding='utf-8-sig') as f:
                            channel_map = json.load(f)
                    except Exception:
                        try:
                            with open(map_path, 'r', encoding='utf-8') as f:
                                channel_map = json.load(f)
                        except Exception:
                            channel_map = {}

                # Build id->name map from logs (best effort)
                id_to_name = {}
                for lf in ['filteredlogs.json', 'd2dlogs.json', 'botlogs.json']:
                    logs_path = os.path.join(root, 'logs', lf)
                    if not os.path.exists(logs_path):
                        continue
                    try:
                        with open(logs_path, 'r', encoding='utf-8') as f:
                            items = json.load(f)
                        if not isinstance(items, list):
                            continue
                        for it in items:
                            sid = it.get('source_channel_id')
                            sname = it.get('source_channel_name')
                            did = it.get('dest_channel_id')
                            dname = it.get('dest_channel_name')
                            if sid and sname:
                                try:
                                    # Only accept non-numeric names
                                    if not str(sname).isnumeric():
                                        id_to_name[str(sid)] = sname
                                except Exception:
                                    id_to_name[str(sid)] = sname
                            if did and dname:
                                try:
                                    if not str(dname).isnumeric():
                                        id_to_name[str(did)] = dname
                                except Exception:
                                    id_to_name[str(did)] = dname
                    except Exception:
                        continue

                # Enrich with DESTINATION guild channels (preferred for names)
                try:
                    if MENTION_BOT_TOKEN and DESTINATION_GUILD_ID:
                        headers = {
                            'Authorization': f'Bot {MENTION_BOT_TOKEN}',
                            'User-Agent': 'RS-Dashboard/1.0'
                        }
                        url = f'https://discord.com/api/v9/guilds/{DESTINATION_GUILD_ID}/channels'
                        r = requests.get(url, headers=headers, timeout=5)
                        if r.status_code == 200:
                            for ch in r.json():
                                cid = str(ch.get('id'))
                                cname = ch.get('name')
                                if cid and cname:
                                    id_to_name[cid] = cname
                except Exception:
                    pass

                # Build destination-centric view using webhook metadata
                destinations = {}
                for src_id_str, webhook_url in (channel_map or {}).items():
                    try:
                        # Extract webhook id and token
                        import re as _re
                        m = _re.search(r"/webhooks/(\d+)/(\w+)", str(webhook_url))
                        dest_cid = None
                        if m:
                            wh_id, wh_token = m.group(1), m.group(2)
                            info_url = f"https://discord.com/api/v9/webhooks/{wh_id}/{wh_token}"
                            try:
                                info_resp = requests.get(info_url, timeout=5)
                                if info_resp.status_code == 200:
                                    info = info_resp.json()
                                    dest_cid = str(info.get('channel_id') or '') or None
                            except Exception:
                                dest_cid = None
                        key = dest_cid or f"webhook:{str(webhook_url)[:18]}..."
                        bucket = destinations.setdefault(key, {
                            'id': dest_cid,
                            'name': id_to_name.get(dest_cid, f"# {dest_cid[-6:]}" if dest_cid else 'Webhook Target'),
                            'sources': []
                        })
                        bucket['sources'].append({'source_channel_id': str(src_id_str), 'webhook': webhook_url})
                    except Exception:
                        continue

                # Legacy categories for backward compatibility (kept)
                all_ids = set([str(k) for k in channel_map.keys()]) | set(id_to_name.keys())
                mapped = []
                unmapped = []
                for cid in sorted(all_ids):
                    name = id_to_name.get(str(cid)) or f"# {str(cid)[-6:]}"
                    entry = {
                        'id': str(cid),
                        'name': name,
                        'in_map': str(cid) in channel_map
                    }
                    if entry['in_map']:
                        mapped.append(entry)
                    else:
                        unmapped.append(entry)

                response = {
                    'destinations': [v for _, v in destinations.items()],
                    'categories': [
                        {'name': 'Mapped', 'channels': mapped},
                        {'name': 'Unmapped', 'channels': unmapped}
                    ]
                }

                payload = json.dumps(response, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                return

        elif self.path.startswith('/startup_status'):
            try:
                root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                # Load map for counts
                channel_map = {}
                try:
                    with open(os.path.join(root, 'config', 'channel_map.json'), 'r', encoding='utf-8-sig') as f:
                        channel_map = json.load(f)
                except Exception:
                    channel_map = {}

                # Helper to load json logs safely
                def load_json_list(p):
                    try:
                        if os.path.exists(p):
                            with open(p, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                            return data if isinstance(data, list) else []
                    except Exception:
                        return []
                    return []

                botlogs = load_json_list(os.path.join(root, 'logs', 'botlogs.json'))
                d2dlogs = load_json_list(os.path.join(root, 'logs', 'd2dlogs.json'))
                filteredlogs = load_json_list(os.path.join(root, 'logs', 'filteredlogs.json'))

                import re
                status = {
                    'mention_bot': {
                        'destination_server_id': None,
                        'server_name': None,
                        'mode': None,
                        'webhook_only': None,
                        'ping_channels': [],
                        'detected': False
                    },
                    'd2d': {
                        'channel_map_count': len(channel_map) if isinstance(channel_map, dict) else 0,
                        'latest_forward_timestamp': None
                    },
                    'filter_forwarder': {
                        'latest_filter_timestamp': None,
                        'link_types_seen': []
                    }
                }

                # Parse mention bot details from botlogs entries (use summary/content)
                for entry in (botlogs[-200:]):
                    text = str(entry.get('summary') or entry.get('content') or '')
                    if not text:
                        continue
                    m = re.search(r'destination server:\s*(\d+)', text, re.IGNORECASE)
                    if m:
                        status['mention_bot']['destination_server_id'] = m.group(1)
                        status['mention_bot']['detected'] = True
                    m = re.search(r'Connected to server:\s*([^\n]+)', text, re.IGNORECASE)
                    if m:
                        status['mention_bot']['server_name'] = m.group(1).strip()
                        status['mention_bot']['detected'] = True
                    if 'Mention Bot Active' in text:
                        status['mention_bot']['mode'] = 'Mention Bot Active'
                        status['mention_bot']['detected'] = True
                    m = re.search(r'WEBHOOK_ONLY\]\s*(True|False)', text)
                    if m:
                        status['mention_bot']['webhook_only'] = (m.group(1) == 'True')
                        status['mention_bot']['detected'] = True
                    m = re.search(r'PING_CHANNELS.*?\[(.*?)\]', text)
                    if m:
                        channels = [s.strip() for s in m.group(1).split(',') if s.strip()]
                        status['mention_bot']['ping_channels'] = channels
                        status['mention_bot']['detected'] = True

                # Latest timestamps
                def latest_ts(items):
                    latest = None
                    for it in items:
                        ts = str(it.get('timestamp') or '')
                        if ts and (latest is None or str(ts) > str(latest)):
                            latest = ts
                    return latest

                status['d2d']['latest_forward_timestamp'] = latest_ts(d2dlogs)
                status['filter_forwarder']['latest_filter_timestamp'] = latest_ts(filteredlogs)
                # link types present
                types = set()
                for it in filteredlogs[-500:]:
                    t = it.get('link_type')
                    if t:
                        types.add(str(t))
                status['filter_forwarder']['link_types_seen'] = sorted(list(types))

                payload = json.dumps({'success': True, 'status': status}, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            except Exception as e:
                payload = json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False).encode('utf-8')
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

        else:
            # Serve static files
            super().do_GET()

    def log_message(self, format, *args):
        """Suppress default logging"""
        pass

def run_server(port=8080):
    # Set up signal handler for graceful shutdown
    def signal_handler(signum, frame):
        print(f"\n[HTTP] Received signal {signum}, shutting down gracefully...")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    with socketserver.TCPServer(("", port), WorkingHTTPRequestHandler) as httpd:
        print(f"[HTTP] Serving on port {port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[HTTP] Server stopped")

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_server(port)
