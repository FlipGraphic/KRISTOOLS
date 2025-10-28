import json
import os
import time
from typing import Dict, Any, Optional

from src.core.config import DISCORD_GUILD_ID, DESTINATION_GUILD_ID

# Define organized log file paths
FILTERED_LOGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "filteredlogs.json")  # Amazon/Mavely/Upcoming filtered messages
D2D_LOGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "d2dlogs.json")            # D2D bridge webhook forwarding
BOT_LOGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "botlogs.json")             # Bot startup/status/terminal logs

def _write_to_log_file(log_path: str, entry: Dict[str, Any], max_entries: int = 200) -> None:
    """Write entry to a specific log file."""
    entry = dict(entry)
    entry["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    
    # Privacy: remove any user-identifying field before persisting
    if "user" in entry:
        entry.pop("user", None)
    
    # Generate Discord message link if we have the required data
    if entry.get("message_id") and entry.get("dest_channel_id"):
        # Prefer destination guild if a destination channel is present
        guild_id_for_link = DESTINATION_GUILD_ID or DISCORD_GUILD_ID
        entry["discord_link"] = (
            f"https://discord.com/channels/{guild_id_for_link}/{entry['dest_channel_id']}/{entry['message_id']}"
        )
    
    # Compute a stable signature for dedupe
    def _sig(e: Dict[str, Any]) -> str:
        return "|".join([
            str(e.get("message_id", "")),
            str(e.get("event", "")),
            str(e.get("link_type", "")),
            str(e.get("source_channel_id", "")),
            str(e.get("dest_channel_id", "")),
            str((e.get("summary") or e.get("content") or ""))[:80],
        ])
    
    try:
        logs = []
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    logs = []
        # Skip writing if an identical signature already exists in recent window
        recent = logs[-50:]
        new_sig = _sig(entry)
        recent_sigs = { _sig(x) for x in recent }
        if new_sig in recent_sigs:
            return
        
        logs.append(entry)
        logs = logs[-max_entries:]  # Keep last N entries
        tmpfile = log_path + ".tmp"
        with open(tmpfile, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2)
        # Windows-safe replace with brief retries to avoid sharing violations
        replaced = False
        for _ in range(10):
            try:
                os.replace(tmpfile, log_path)
                replaced = True
                break
            except Exception:
                time.sleep(0.05)
        if not replaced:
            try:
                with open(log_path, "w", encoding="utf-8") as f:
                    json.dump(logs, f, indent=2)
            except Exception:
                pass
    except Exception as e:
        print(f"[WARNING] Failed to write log to {log_path}: {e}")

def write_filtered_log(entry: Dict[str, Any]) -> None:
    """Write to filtered logs (Amazon, Mavely, Upcoming messages)."""
    _write_to_log_file(FILTERED_LOGS_PATH, entry)

def write_d2d_log(entry: Dict[str, Any]) -> None:
    """Write to D2D bridge logs (webhook forwarding from source channels)."""
    _write_to_log_file(D2D_LOGS_PATH, entry)

def write_bot_log(entry: Dict[str, Any]) -> None:
    """Write to bot logs (startup, status, terminal logs, backend events)."""
    _write_to_log_file(BOT_LOGS_PATH, entry)


def write_enhanced_log(
    message_id: str,
    source_channel_id: int,
    source_channel_name: str,
    dest_channel_id: Optional[int] = None,
    dest_channel_name: Optional[str] = None,
    user: str = "Unknown",
    content: str = "",
    link_type: Optional[str] = None,
    webhook_url: Optional[str] = None,
    embeds: Optional[Any] = None,
    **kwargs
) -> None:
    """Write an enhanced log entry with all metadata to appropriate log file."""
    entry = {
        "message_id": message_id,
        "source_channel_id": source_channel_id,
        "source_channel_name": source_channel_name,
        "dest_channel_id": dest_channel_id,
        "dest_channel_name": dest_channel_name,
        "user": user,
        "content": content[:200] + "..." if len(content) > 200 else content,  # Truncate long content
        "link_type": link_type,
        "webhook_url": webhook_url,
        **kwargs
    }
    # Add embeds if provided (for filter bot processing)
    if embeds is not None:
        entry["embeds"] = embeds
    
    # Determine which log file to use based on event type
    event_type = kwargs.get("event", "")
    if event_type == "filter_classify" or link_type in ["AMAZON", "MAVELY", "UPCOMING"]:
        write_filtered_log(entry)
    elif event_type == "webhook_forward" or webhook_url:
        write_d2d_log(entry)
    else:
        # Default to bot logs for system events
        write_bot_log(entry)
