import os
import json
from typing import Dict, List, Optional

try:
    # Lazy import to keep optional dependency
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None

ROOT_DIR = os.path.dirname(__file__)

# Prefer tokenkeys.env, fallback to .env
ENV_TOKENKEYS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "tokenkeys.env")
ENV_DOTENV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", ".env")

# Load environment files if python-dotenv is available
if load_dotenv is not None:
    # Load legacy .env first with lower priority
    if os.path.exists(ENV_DOTENV):
        load_dotenv(ENV_DOTENV, override=False)
    # Load tokenkeys.env second with higher priority
    if os.path.exists(ENV_TOKENKEYS):
        load_dotenv(ENV_TOKENKEYS, override=True)


def _str_to_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


# General settings
VERBOSE: bool = _str_to_bool(os.getenv("VERBOSE", "true"), True)
CHANNEL_MAP_PATH: str = os.getenv("CHANNEL_MAP_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "channel_map.json"))

# Tokens
DISCORD_TOKEN: str = (os.getenv("DISCORD_TOKEN", "").strip())
# Do NOT default to DISCORD_TOKEN; the forwarder requires a real bot token
MENTION_BOT_TOKEN: str = (os.getenv("MENTION_BOT_TOKEN", "").strip())



# Discord Server (Guild) IDs - Different servers for different bots
SOURCE_GUILD_ID: str = (os.getenv("SOURCE_GUILD_ID", "").strip())  # Where messages originate
DESTINATION_GUILD_ID: str = (os.getenv("DESTINATION_GUILD_ID", "").strip())  # RS Pinger/Notes server

# Legacy: Keep DISCORD_GUILD_ID for backwards compatibility (maps to SOURCE_GUILD_ID)
DISCORD_GUILD_ID: str = SOURCE_GUILD_ID or (os.getenv("DISCORD_GUILD_ID", "").strip())

# Smart forwarder targets (channel-based; not webhooks)
# If set to non-zero, smart forwarder will deliver to these channels
def _env_int(name: str, default: int = 0) -> int:
    try:
        value = int((os.getenv(name, str(default)) or str(default)).strip())
        return value if value > 0 else 0
    except Exception:
        return 0

SMART_AMAZON_CHANNEL_ID: int = _env_int("SMART_AMAZON_CHANNEL_ID", 0)
SMART_MAVELY_CHANNEL_ID: int = _env_int("SMART_MAVELY_CHANNEL_ID", 0)
SMART_UPCOMING_CHANNEL_ID: int = _env_int("SMART_UPCOMING_CHANNEL_ID", 0)
SMART_DEFAULT_CHANNEL_ID: int = _env_int("SMART_DEFAULT_CHANNEL_ID", 0)

# Legacy webhook settings (kept for backwards-compatibility with d2d importers - not actively used)
# These are not used in the current implementation but kept for compatibility
# AMAZON_WEBHOOK: str = (os.getenv("AMAZON_WEBHOOK", "").strip())
# MAVELY_WEBHOOK: str = (os.getenv("MAVELY_WEBHOOK", "").strip())
# UPCOMING_WEBHOOK: str = (os.getenv("UPCOMING_WEBHOOK", "").strip())

# Mention bot settings
VISIBLE_DELAY: int = int(os.getenv("VISIBLE_DELAY", "5") or 5)
COOLDOWN_SECONDS: int = int(os.getenv("COOLDOWN_SECONDS", "10") or 10)

# Comma-separated list of channel IDs
_raw_ping_channels = os.getenv("PING_CHANNELS", "").strip()
PING_CHANNELS: List[int] = []
if _raw_ping_channels:
    for piece in _raw_ping_channels.replace("\n", ",").split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            PING_CHANNELS.append(int(piece))
        except ValueError:
            # ignore malformed entries
            pass

# SMART_SOURCE_CHANNELS - Removed (not used, filterbot handles all channels)


def _coerce_channel_map_keys_to_ints(raw_map: Dict) -> Dict[int, str]:
    result: Dict[int, str] = {}
    for key, value in raw_map.items():
        try:
            result[int(key)] = str(value)
        except Exception:
            # Skip keys that are not numeric or values that are not strings
            continue
    return result


def load_channel_map(path: str = CHANNEL_MAP_PATH) -> Dict[int, str]:
    try:
        # Be tolerant of BOM and different editors
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        return _coerce_channel_map_keys_to_ints(data)
    except FileNotFoundError:
        return {}
    except Exception:
        # If the JSON is invalid, return empty map to fail safe
        return {}


CHANNEL_MAP: Dict[int, str] = load_channel_map()

# ===== Optional Mavely converter integration (legacy - not actively used) =====
# These are kept for potential future use but not currently implemented
# MAVELY_BC_ID: str = os.getenv("MAVELY_BC_ID", "").strip()
# MAVELY_CONVERTER_URL: str = os.getenv("MAVELY_CONVERTER_URL", "").strip()
# MAVELY_CONVERTER_API_KEY: str = os.getenv("MAVELY_CONVERTER_API_KEY", "").strip()
