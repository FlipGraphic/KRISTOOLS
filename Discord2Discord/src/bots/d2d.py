"""Discord2Discord Bridge (v3.4) with Integrated Filter Bot.

Environment/config is loaded via config.py (.env-backed). This script forwards
messages from specific channels (CHANNEL_MAP) to target webhooks and also
uses filterbot.py to classify and route messages to organized channels.
"""

import signal
import sys
import os
import time
import atexit
import requests
import discum

from src.core.config import DISCORD_TOKEN, CHANNEL_MAP, VERBOSE, DISCORD_GUILD_ID, DESTINATION_GUILD_ID
from src.core.log_utils import write_enhanced_log, write_bot_log, write_d2d_log
from src.core.filterbot import filter_and_classify
import re
import threading

# ================= Single-instance Lock =================
_LOCK_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                               ".d2d.lock")

def _cleanup_lock_file():
    try:
        if os.path.exists(_LOCK_FILE_PATH):
            os.remove(_LOCK_FILE_PATH)
    except Exception:
        pass

def _acquire_single_instance_lock() -> None:
    """Prevent multiple concurrent d2d instances from running.

    Uses an atomic lock file create (O_CREAT|O_EXCL). If the file already exists,
    we assume another instance is running and exit quietly.
    """
    try:
        fd = os.open(_LOCK_FILE_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w") as f:
            f.write(f"pid={os.getpid()}\nstart={int(time.time())}\n")
        atexit.register(_cleanup_lock_file)
    except FileExistsError:
        print("[WARN] Another d2d instance appears to be running. Exiting to avoid duplicates.")
        sys.exit(0)
    except Exception:
        # If lock cannot be established, proceed but warn
        print("[WARN] Unable to create lock file; continuing without single-instance guard.")

if not (DISCORD_TOKEN or "").strip():
    print("[ERROR] DISCORD_TOKEN is not set in environment/.env")
    sys.exit(1)

# Acquire single-instance lock as early as possible
_acquire_single_instance_lock()

bot = discum.Client(token=DISCORD_TOKEN, log=False)

# ================= Graceful Exit =================
def sigint_handler(signum, frame):
    print("\n[STOP] Ctrl+C detected. Exiting cleanly.")
    try:
        _cleanup_lock_file()
    except Exception:
        pass
    sys.exit(0)
signal.signal(signal.SIGINT, sigint_handler)

# ================= Logging =================
# Centralized via log_utils.write_log

# ================= Main Event Handler =================
@bot.gateway.command
def bridge_listener(resp):
    if resp.event.ready_supplemental:
        user = bot.gateway.session.user
        print(f"[LOGIN] {user['username']}#{user['discriminator']}")
        print("[MODE] Discord2Discord Bridge v3.4 with Filter Bot Active\n")
        try:
            write_bot_log({"event": "bot_ready", "user": f"{user['username']}#{user['discriminator']}"})
        except Exception:
            pass
        try:
            print(f"[INFO] Loaded {len(CHANNEL_MAP)} source->webhook mappings from channel_map.json")
            src_guild = DISCORD_GUILD_ID or "(unset)"
            print(f"[INFO] Source Guild ID: {src_guild}")
            print("[INFO] Listening for new messages in source channels...\n")
            write_bot_log({"event": "bridge_listening", "channel_map_count": len(CHANNEL_MAP)})
            def heartbeat():
                while True:
                    print("[HEARTBEAT] Listening... (waiting for messages)")
                    # Log heartbeat to bot logs
                    write_bot_log({"event": "heartbeat", "bot_name": "d2d.py", "status": "listening", "channels_monitored": len(CHANNEL_MAP)})
                    time.sleep(60)
            threading.Thread(target=heartbeat, daemon=True).start()
        except Exception:
            pass

    if not resp.event.message:
        return

    m = resp.parsed.auto()

    guildID = m.get("guild_id")
    chan_id = m.get("channel_id")
    try:
        channelID = int(chan_id)
    except Exception:
        return

    # Get message details for backend logging
    author = m.get("author", {})
    username = author.get("username", "Unknown")
    is_webhook = bool(m.get("webhook_id")) or author.get("bot", False)
    is_monitored = channelID in CHANNEL_MAP
    
    # Log message detection to bot logs (include source_* for dashboard rendering)
    write_bot_log({
        "event": "message_detected",
        "channel_id": channelID,
        "source_channel_id": channelID,
        "source_channel_name": None,
        "user": username,
        "is_monitored": is_monitored,
        "is_webhook": is_webhook,
        "action": "detected"
    })

    # Check if message is in CHANNEL_MAP (webhook forwarding)
    if channelID in CHANNEL_MAP:
        # Allow webhook messages from monitored channels - don't skip them
        # Forward to webhook (original d2d functionality)
        _forward_to_webhook(m, channelID, guildID)
        write_bot_log({
            "event": "message_detected",
            "channel_id": channelID,
            "source_channel_id": channelID,
            "user": username,
            "is_monitored": True,
            "is_webhook": is_webhook,
            "action": "forwarded"
        })
    
    # Also check if message should be filtered and classified
    try:
        filter_result = filter_and_classify(m)
        if filter_result:
            _forward_to_classified_channel(m, filter_result)
            write_bot_log({
                "event": "message_classified",
                "message_id": m.get("id", "unknown"),
                "category": filter_result.get("category", "unknown")
            })
    except Exception as e:
        print(f"[ERROR] Filter classification failed: {e}")
        write_bot_log({
            "event": "error",
            "bot_name": "d2d.py",
            "error_type": "filter_classification",
            "error_message": str(e)
        })


def _forward_to_webhook(m, channelID, guildID):
    """Forward message to webhook (original d2d functionality)."""
    author = m.get("author", {})
    username = author.get("username", "Unknown")
    avatar = (
        f"https://cdn.discordapp.com/avatars/{author.get('id')}/{author.get('avatar')}.png"
        if author.get("avatar") else None
    )
    content = m.get("content", "")
    attachments = m.get("attachments", [])
    embeds = m.get("embeds", [])

    try:
        guild_data = bot.gateway.session.guild(guildID)
        channelName = guild_data["channels"][channelID]["name"] if guild_data and "channels" in guild_data else str(channelID)
    except Exception:
        channelName = str(channelID)

    webhook = CHANNEL_MAP[channelID]
    msg_text = content

    embed_list = []
    for e in embeds:
        embed = {}
        if e.get("title"): embed["title"] = e["title"]
        if e.get("url"): embed["url"] = e["url"]
        if e.get("description"): embed["description"] = e["description"]
        if "image" in e and e["image"].get("url"):
            embed["image"] = {"url": e["image"]["url"]}
        embed_list.append(embed)

    payload = {
        "username": username,
        "avatar_url": avatar,
        "content": msg_text,
        "embeds": embed_list[:10],
    }

    # In-process duplicate guard for direct webhook forwarding (message id based)
    # Helps avoid accidental double posts in the same process (e.g., reconnect quirks)
    global _recent_forward_ids
    try:
        _recent_forward_ids
    except NameError:
        _recent_forward_ids = {}
    try:
        msg_id_key = str(m.get("id", ""))
        now_ts = time.time()
        # prune old entries (> 30s)
        for k, ts in list(_recent_forward_ids.items()):
            if now_ts - ts > 30:
                _recent_forward_ids.pop(k, None)
        if msg_id_key:
            if msg_id_key in _recent_forward_ids:
                if VERBOSE:
                    print(f"[WEBHOOK-SKIP] Duplicate message_id {msg_id_key} within 30s window")
                return
            _recent_forward_ids[msg_id_key] = now_ts
    except Exception:
        pass

    # Destination channel info (resolved from webhook response or metadata)
    dest_channel_id = None
    dest_channel_name = "Unknown"

    message_id = None
    success = False
    error_msg = None
    try:
        r = requests.post(webhook, json=payload, timeout=10)
        # Discord webhooks can return 200 (with message data) or 204 (no content) for success
        if r.status_code in [200, 204]:
            success = True
            # Extract message ID from webhook response (only if status is 200)
            if r.status_code == 200:
                try:
                    response_data = r.json()
                    message_id = response_data.get("id")
                    # Capture destination channel from response when available
                    cid = response_data.get("channel_id")
                    if cid and not dest_channel_id:
                        try:
                            dest_channel_id = int(cid)
                        except Exception:
                            dest_channel_id = None
                except:
                    pass
        else:
            error_msg = f"HTTP {r.status_code}"
        if VERBOSE:
            print(f"[WEBHOOK] #{channelName} | {username} [{r.status_code}]")
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Failed to send via webhook: {e}")

    # Fallback: resolve destination channel via webhook info endpoint
    if dest_channel_id is None:
        try:
            wh_match = re.search(r"/webhooks/(\d+)/(\w+)", webhook)
            if wh_match:
                wh_id, wh_token = wh_match.group(1), wh_match.group(2)
                info_url = f"https://discord.com/api/v9/webhooks/{wh_id}/{wh_token}"
                info_resp = requests.get(info_url, timeout=5)
                if info_resp.status_code == 200:
                    info = info_resp.json()
                    cid = info.get("channel_id")
                    if cid:
                        try:
                            dest_channel_id = int(cid)
                        except Exception:
                            dest_channel_id = None
        except Exception:
            pass

    # Best-effort: set destination channel name from session cache when id is known
    if dest_channel_id is not None:
        try:
            if hasattr(bot.gateway, 'session') and bot.gateway.session:
                target_guild_id = DESTINATION_GUILD_ID or DISCORD_GUILD_ID
                guild_data = bot.gateway.session.guild(target_guild_id)
                if guild_data and "channels" in guild_data:
                    dest_channel_name = guild_data["channels"].get(dest_channel_id, {}).get("name", f"Channel {dest_channel_id}")
        except Exception:
            dest_channel_name = f"Channel {dest_channel_id}"
    
    # Log webhook forwarding attempt to bot logs
    write_bot_log({
        "event": "webhook_forward",
        "channel_id": channelID,
        "webhook_url": webhook[:50] + "..." if len(webhook) > 50 else webhook,
        "success": success,
        "error": error_msg
    })

    # Compose D2D summary for dashboard
    try:
        msg_id_for_summary = str(m.get("id", "unknown"))
    except Exception:
        msg_id_for_summary = "unknown"
    status_text = "successfully posted" if success else (error_msg or "failed")
    if (dest_channel_name == "Unknown" or not dest_channel_name) and dest_channel_id is not None:
        dest_channel_name = f"Channel {dest_channel_id}"
    summary = f"D2D - #{channelName} (msg {msg_id_for_summary}) detected - {status_text} - webhook -> #{dest_channel_name or 'Unknown'}"
    try:
        print(summary)
    except Exception:
        pass

    # Also mirror a minimal entry to D2D logs immediately so the dashboard can surface activity
    try:
        write_d2d_log({
            "message_id": msg_id_for_summary,
            "source_channel_id": channelID,
            "source_channel_name": channelName,
            "dest_channel_id": dest_channel_id,
            "dest_channel_name": dest_channel_name,
            "user": username,
            "guild_id": guildID,
            "content": content or "[embed/attachment]",
            "link_type": ("D2D" if success else "ERROR"),
            "event": ("webhook_forward" if success else "error"),
            "success": success,
            "summary": summary,
            "error": (error_msg if not success else None)
        })
    except Exception:
        pass

    for a in attachments:
        url = a.get("url")
        if not url:
            continue
        try:
            attach_response = requests.post(webhook, json={"username": username, "avatar_url": avatar, "content": url}, timeout=10)
            if attach_response.status_code not in [200, 204]:
                print(f"[ERROR] Attachment failed with HTTP {attach_response.status_code}: {url}")
            elif VERBOSE:
                print(f"[ATTACH] {url}")
        except Exception as e:
            print(f"[ERROR] Attachment failed: {e}")

    # Use D2D logging for webhook forwarding with best-known destination info
    try:
        final_message_id = str(message_id) if message_id else msg_id_for_summary
        final_summary = f"D2D - #{channelName} (msg {final_message_id}) detected - {status_text} - webhook -> #{dest_channel_name or 'Unknown'}"
        write_d2d_log({
            "message_id": final_message_id,
            "source_channel_id": channelID,
            "source_channel_name": channelName,
            "dest_channel_id": dest_channel_id,
            "dest_channel_name": dest_channel_name,
            "user": username,
            "guild_id": guildID,
            "content": content or "[embed/attachment]",
            "link_type": ("D2D" if success else "ERROR"),
            "webhook_url": webhook,
            "event": ("webhook_forward" if success else "error"),
            "success": success,
            "summary": final_summary,
            "error": (error_msg if not success else None)
        })
        try:
            print(final_summary)
        except Exception:
            pass
    except Exception:
        pass


def _forward_to_classified_channel(m, filter_result):
    """Forward message to classified channel based on filter result."""
    try:
        author = m.get("author", {})
        username = author.get("username", "Unknown")
        channelID = m.get("channel_id")
        
        try:
            guild_data = bot.gateway.session.guild(m.get("guild_id"))
            channelName = guild_data["channels"][channelID]["name"] if guild_data and "channels" in guild_data else str(channelID)
        except Exception:
            channelName = str(channelID)

        if VERBOSE:
            # Use ASCII-safe characters to avoid Unicode encoding issues
            print(f"[FILTER] #{channelName} | {username} -> {filter_result['tag']} (Channel {filter_result['channel_id']})")
    except Exception as e:
        print(f"[ERROR] Failed to process classified channel forward: {e}")
        return

    # Log the filter classification with embeds data
    write_enhanced_log(
        message_id=str(m.get("id", "unknown")),
        source_channel_id=channelID,
        source_channel_name=channelName,
        dest_channel_id=filter_result['channel_id'],
        dest_channel_name=f"Filtered-{filter_result['tag']}",
        user=username,
        content=filter_result['content'] or "[embed/attachment]",
        link_type=filter_result['tag'],
        event="filter_classify",
        embeds=filter_result.get('embeds', [])  # Include embeds for filter_bot
    )
# ================= Runtime Loop (Auto-restart on Socket Error) =================
if __name__ == "__main__":
    print("[START] Discord2Discord Bridge v3.4 with Filter Bot")
    try:
        write_bot_log({"event": "bridge_start"})
    except Exception:
        pass
    while True:
        try:
            bot.gateway.run(auto_reconnect=True)
            break
        except KeyboardInterrupt:
            print("[STOP] Manually terminated.")
            sys.exit(0)
        except Exception as e:
            err = str(e).lower()
            if "socket is already opened" in err:
                print("[WARN] Socket already opened, retrying in 5 seconds...")
                write_bot_log({"event": "socket_restart", "error": err})
                time.sleep(5)
                continue
            else:
                print(f"[ERROR] {e}")
                time.sleep(3)
