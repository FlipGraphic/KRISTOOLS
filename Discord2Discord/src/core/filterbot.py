"""Filter Bot - Message Classification and Filtering Logic

This module contains the filtering logic extracted from smart_forwarder.py
and provides a clean interface for d2d.py to classify messages.
"""

import re
import time
import hashlib
from typing import Dict, Any, List, Optional, Tuple

from src.core.config import (
    VERBOSE,
    SMART_AMAZON_CHANNEL_ID,
    SMART_MAVELY_CHANNEL_ID,
    SMART_UPCOMING_CHANNEL_ID,
    SMART_DEFAULT_CHANNEL_ID,
)

# Compile patterns once for efficiency
AMAZON_PATTERN = re.compile(
    r"(https?:\/\/(?:www\.)?(amazon\.com|amzn\.to)\/[^\s]+|\bB0[A-Z0-9]{8}\b)",
    re.IGNORECASE,
)
TIMESTAMP_PATTERN = re.compile(
    r"("  # Match any of the following indicators of time/schedule
    r"<t:\d+:[a-zA-Z]>"  # Discord time tag
    r"|\bup\s*next\b"  # 'UP NEXT'
    r"|\b(in|within)\s+\d+\s*(minutes?|mins?|hours?|hrs?|days?)\b"  # in 2 hours
    r"|\btoday\b"  # today
    r"|\b\d{1,2}:\d{2}\s*(am|pm)\b"  # 11:00 AM
    r"|drop(?:ping)?"  # drop/dropping
    r"|release"  # release
    r"|tomorrow"  # tomorrow
    r"|\b\d{1,2}\/\d{1,2}\b"  # 10/27
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b"  # month names
    r")",
    re.IGNORECASE,
)

# Common store domains to explicitly route to MAVELY
STORE_DOMAINS = [
    # General retailers (Amazon handled separately by AMAZON_PATTERN)
    r"walmart\.com", r"target\.com", r"bestbuy\.com",
    r"lowes\.com", r"homedepot\.com", r"costco\.com", r"samsclub\.com", r"wayfair\.com",
    # Footwear and apparel
    r"nike\.com", r"adidas\.com", r"footlocker\.com", r"finishline\.com", r"jdports?\.com",
    r"snkrs?\.com", r"stockx\.com", r"goat\.com", r"hibbett\.com", r"eastbay\.com",
    r"newbalance\.com", r"reebok\.com", r"puma\.com",
    # Fashion/beauty
    r"macy[s]?\.com", r"nordstrom\.com", r"sephora\.com", r"ulta\.com",
    # Misc deal/link shorteners often used by stores
    r"bit\.ly", r"linktr\.ee", r"l\.instagram\.com", r"shop-links?\.co",
]

STORE_DOMAIN_PATTERN = re.compile(r"https?://[^\s]*(" + "|".join(STORE_DOMAINS) + r")[^\s]*", re.IGNORECASE)

# Duplicate detection
_recent_msgs: Dict[str, float] = {}
DUPLICATE_WINDOW_SECONDS = 10


def _hash_message(content: str, embeds: List[Dict[str, Any]]) -> str:
    """Create a hash of message content for duplicate detection."""
    embed_text = "".join(
        (e.get("title", "") or "") + (e.get("description", "") or "") + (e.get("url", "") or "")
        for e in embeds
    )
    return hashlib.md5((content + embed_text).encode("utf-8")).hexdigest()


def _select_target_channel_id(text_to_check: str, attachments: List[Dict[str, Any]]) -> Optional[Tuple[int, str]]:
    """Determine which channel a message should be sent to based on content."""
    if TIMESTAMP_PATTERN.search(text_to_check) and SMART_UPCOMING_CHANNEL_ID:
        return SMART_UPCOMING_CHANNEL_ID, "UPCOMING"
    if AMAZON_PATTERN.search(text_to_check) and SMART_AMAZON_CHANNEL_ID:
        return SMART_AMAZON_CHANNEL_ID, "AMAZON"
    # If any URL matches common store domains, consider it a MAVELY candidate
    try:
        att_text = " ".join([a.get("url", "") for a in (attachments or [])])
        if STORE_DOMAIN_PATTERN.search(text_to_check + " " + att_text) and SMART_MAVELY_CHANNEL_ID:
            return SMART_MAVELY_CHANNEL_ID, "MAVELY"
    except Exception:
        pass
    if ("http" in text_to_check or any(a.get("url") for a in attachments)) and SMART_MAVELY_CHANNEL_ID:
        return SMART_MAVELY_CHANNEL_ID, "MAVELY"
    if SMART_DEFAULT_CHANNEL_ID:
        return SMART_DEFAULT_CHANNEL_ID, "DEFAULT"
    return None


def _format_embeds(embeds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format embeds for webhook payload."""
    result: List[Dict[str, Any]] = []
    for e in embeds:
        embed: Dict[str, Any] = {}
        if e.get("title"):
            embed["title"] = e["title"]
        if e.get("url"):
            embed["url"] = e["url"]
        if e.get("description"):
            embed["description"] = e["description"]
        if "image" in e and isinstance(e["image"], dict) and e["image"].get("url"):
            embed["image"] = {"url": e["image"]["url"]}
        result.append(embed)
    return result[:10]


def should_filter_message(message_data: Dict[str, Any]) -> bool:
    """Check if message should be filtered out (spam, duplicates, etc.)."""
    try:
        author = message_data.get("author", {}) or {}
        author_name = author.get("username", "Unknown")
        author_id = author.get("id", "0")

        # Hard filters: skip obvious vendor providers, replies, mass mentions
        if (
            author_name.lower().startswith(("rs pinger", "flipflip", "flipfluence", "divine", "smart forwarder"))
        ):
            return True

        content = (message_data.get("content", "") or "").strip()
        embeds: List[Dict[str, Any]] = message_data.get("embeds", []) or []
        attachments: List[Dict[str, Any]] = message_data.get("attachments", []) or []

        if not content and not embeds and not attachments:
            return True
        if re.fullmatch(r"(<@[!&]?\d+>|@everyone|@here)+", content):
            return True
        if message_data.get("message_reference"):
            return True

        # Skip embeds from certain providers (avoid obvious vendor/system mirrors)
        if any(
            (e.get("provider", {}) or {}).get("name", "").lower().startswith(
                ("discord", "paypal", "flipflip", "flipfluence", "divine", "twitter", "instagram")
            )
            for e in embeds
        ):
            return True

        # Duplicate detection
        msg_hash = _hash_message(content, embeds)
        key = f"{author_id}-{msg_hash}"
        now = time.time()
        last = _recent_msgs.get(key, 0)
        if now - last < DUPLICATE_WINDOW_SECONDS:
            if VERBOSE:
                print(f"[FILTER-SKIP] {author_name} duplicate within {round(now - last,1)}s")
            return True
        _recent_msgs[key] = now

        return False

    except Exception as e:
        print(f"[FILTER-ERROR] {e}")
        return True


def classify_message(message_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Classify a message and return target channel info if it should be forwarded."""
    try:
        author = message_data.get("author", {}) or {}
        author_name = author.get("username", "Unknown")
        author_id = author.get("id", "0")

        content = (message_data.get("content", "") or "").strip()
        embeds: List[Dict[str, Any]] = message_data.get("embeds", []) or []
        attachments: List[Dict[str, Any]] = message_data.get("attachments", []) or []

        text_to_check = content + " ".join(
            str(e.get("title", "")) + str(e.get("description", "")) + str(e.get("url", ""))
            for e in embeds
        )

        selection = _select_target_channel_id(text_to_check, attachments)
        if not selection:
            if VERBOSE:
                print(f"[FILTER-SKIP] {author_name} | No target channel configured")
            return None

        target_channel_id, tag = selection

        avatar = (
            f"https://cdn.discordapp.com/avatars/{author_id}/{author.get('avatar')}.png"
            if author.get("avatar")
            else None
        )

        return {
            "channel_id": target_channel_id,
            "tag": tag,
            "avatar_url": avatar,
            "embeds": _format_embeds(embeds),
            "content": content,
            "attachments": attachments,
            "username": author_name,
        }

    except Exception as e:
        print(f"[FILTER-ERROR] {e}")
        return None


def filter_and_classify(message_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Main function: filter message and classify if it should be forwarded."""
    if should_filter_message(message_data):
        return None
    
    return classify_message(message_data)

