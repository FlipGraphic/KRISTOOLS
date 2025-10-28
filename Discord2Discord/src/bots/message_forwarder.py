"""Message Forwarder - Reads webhook messages from destination channels and filters them.

This bot monitors webhook messages in destination channels and classifies them
using filterbot.py, then forwards to appropriate destination channels.
"""

import os
import sys
import asyncio
from typing import Dict, Any, Optional, List

import discord
from discord.ext import commands

from src.core.config import (
    MENTION_BOT_TOKEN,
    DESTINATION_GUILD_ID,
    SMART_AMAZON_CHANNEL_ID,
    SMART_MAVELY_CHANNEL_ID,
    SMART_UPCOMING_CHANNEL_ID,
    SMART_DEFAULT_CHANNEL_ID,
    VERBOSE,
)
from src.core.filterbot import filter_and_classify
from src.core.log_utils import write_bot_log, write_filtered_log

class MessageForwarder:
    def __init__(self):
        self.token = (MENTION_BOT_TOKEN or "").strip()
        if not self.token:
            print("[ERROR] MENTION_BOT_TOKEN is not set in tokenkeys.env")
            sys.exit(1)
        
        self.processed_ids = set()
        self.destination_channels = {
            "AMAZON": SMART_AMAZON_CHANNEL_ID,
            "MAVELY": SMART_MAVELY_CHANNEL_ID,
            "UPCOMING": SMART_UPCOMING_CHANNEL_ID,
            "DEFAULT": SMART_DEFAULT_CHANNEL_ID,
        }
        
        # Discord bot setup
        intents = discord.Intents.default()
        if hasattr(intents, "message_content"):
            intents.message_content = True
        else:
            intents.messages = True
        
        self.bot = commands.Bot(command_prefix="!", intents=intents)
        self._setup_events()
    
    def _setup_events(self):
        @self.bot.event
        async def on_ready():
            print("=====================================================")
            print(f"[LOGIN] Message Forwarder logged in as {self.bot.user}")
            print(f"[SERVER] Destination server: {DESTINATION_GUILD_ID}")
            print("[MODE] Monitoring webhook messages in destination channels")
            print("=====================================================\n")
            try:
                write_bot_log({"event": "message_forwarder_start", "user": str(self.bot.user)})
            except Exception:
                pass
        
        @self.bot.event
        async def on_message(message):
            # Ignore our own messages
            if message.author == self.bot.user:
                return
            
            # Must be in destination guild
            if not message.guild or str(message.guild.id) != DESTINATION_GUILD_ID:
                return
            
            # Monitor all channels in the destination guild
            # (The webhook forwarding will determine which channels get messages)
            
            # Only process webhook or bot-origin messages to avoid user chatter and loops
            is_webhook = bool(getattr(message, 'webhook_id', None))
            is_bot_msg = bool(getattr(getattr(message, 'author', None), 'bot', False))
            if not (is_webhook or is_bot_msg):
                return
            
            # Skip if already processed
            if message.id in self.processed_ids:
                return
            
            self.processed_ids.add(message.id)
            
            if VERBOSE:
                try:
                    print(f"[FORWARDER] #{message.channel.name} webhook message detected")
                except Exception:
                    print(f"[FORWARDER] Channel {message.channel.id} webhook message detected")
            
            # Convert Discord message to filterbot payload
            payload = self._to_filter_payload(message)
            
            # Classify the message
            result = filter_and_classify(payload)
            if not result:
                return
            
            # Get destination channel
            tag = result.get("tag")
            dest_channel_id = self.destination_channels.get(tag, 0)
            
            if not dest_channel_id:
                if VERBOSE:
                    print(f"[FORWARDER] No channel configured for {tag}")
                try:
                    # Surface to dashboard Errors panel as actionable item
                    write_filtered_log({
                        "event": "error",
                        "source_channel_id": message.channel.id,
                        "dest_channel_id": 0,
                        "tag": tag,
                        "content": (message.content or "")[:200],
                        "link_type": "ERROR",
                        "success": False,
                        "summary": f"No target channel configured for {tag} (src #{message.channel.id})",
                        "error": "no_target_channel"
                    })
                except Exception:
                    pass
                return
            
            # Prevent immediate self-loop if destination equals source
            if dest_channel_id == message.channel.id:
                return
            
            # Send to destination channel
            await self._send_to_destination(message, result, dest_channel_id)
    
    def _to_filter_payload(self, message: discord.Message) -> Dict[str, Any]:
        """Convert Discord message to filterbot payload format."""
        author = message.author
        avatar_hash = None
        try:
            if getattr(author, "avatar", None) and getattr(author.avatar, "key", None):
                avatar_hash = author.avatar.key
        except Exception:
            avatar_hash = None
        
        # Convert embeds
        embeds = []
        for e in message.embeds:
            embed_data = {}
            if e.title:
                embed_data["title"] = e.title
            if e.url:
                embed_data["url"] = e.url
            if e.description:
                embed_data["description"] = e.description
            if e.image and e.image.url:
                embed_data["image"] = {"url": e.image.url}
            embeds.append(embed_data)
        
        # Convert attachments
        attachments = []
        for a in message.attachments:
            if hasattr(a, "url") and a.url:
                attachments.append({"url": a.url})
        
        return {
            "id": str(message.id),
            "guild_id": str(message.guild.id) if message.guild else None,
            "channel_id": message.channel.id,
            "content": message.content or "",
            "embeds": embeds,
            "attachments": attachments,
            "message_reference": bool(message.reference),
            "author": {
                "id": str(author.id),
                "username": getattr(author, "name", getattr(author, "display_name", "Unknown")) or "Unknown",
                "avatar": avatar_hash,
            },
        }
    
    async def _send_to_destination(self, source_message: discord.Message, result: Dict[str, Any], dest_channel_id: int):
        """Send classified message to destination channel."""
        dest_channel = self.bot.get_channel(int(dest_channel_id))
        if not dest_channel:
            print(f"[ERROR] Destination channel {dest_channel_id} not found")
            return
        
        # Build embeds for Discord
        embeds_to_send = []
        for e in result.get("embeds", []) or []:
            embed = discord.Embed(title=e.get("title"), description=e.get("description"))
            if e.get("url"):
                embed.url = e["url"]
            if e.get("image") and isinstance(e.get("image"), dict) and e["image"].get("url"):
                embed.set_image(url=e["image"]["url"])
            embeds_to_send.append(embed)
        
        try:
            await dest_channel.send(content=result.get("content", ""), embeds=embeds_to_send[:10])
            try:
                tag = result.get("tag")
                src_id = source_message.channel.id
                dst_id = int(dest_channel_id)
                dst_name = getattr(dest_channel, 'name', str(dst_id))
                summary = f"FilteredLink-{tag}-#{src_id}-successfully forwarded -> #{dst_name}"
                if VERBOSE:
                    print(summary)
                write_filtered_log({
                    "event": "message_forwarder_forward",
                    "message_id": str(source_message.id),
                    "source_channel_id": src_id,
                    "source_channel_name": getattr(source_message.channel, 'name', str(src_id)),
                    "dest_channel_id": dst_id,
                    "dest_channel_name": dst_name,
                    "guild_id": str(source_message.guild.id) if source_message.guild else None,
                    "tag": tag,
                    "content": (result.get("content", "") or "")[:200],
                    "link_type": tag,
                    "success": True,
                    "summary": summary,
                })
            except Exception:
                pass
        except Exception as e:
            print(f"[ERROR] Failed to send filtered message: {e}")
            try:
                tag = result.get("tag")
                src_id = source_message.channel.id
                dst_id = int(dest_channel_id)
                dst_name = getattr(dest_channel, 'name', str(dst_id)) if dest_channel else str(dst_id)
                summary = f"FilteredLink-{tag}-#{src_id}-failed -> #{dst_name}"
                print(summary)
                write_filtered_log({
                    "event": "error",
                    "message_id": str(source_message.id),
                    "source_channel_id": src_id,
                    "source_channel_name": getattr(source_message.channel, 'name', str(src_id)),
                    "dest_channel_id": dst_id,
                    "dest_channel_name": dst_name,
                    "guild_id": str(source_message.guild.id) if source_message.guild else None,
                    "tag": tag,
                    "content": (result.get("content", "") or "")[:200],
                    "link_type": "ERROR",
                    "success": False,
                    "summary": summary,
                    "error": str(e),
                })
            except Exception:
                pass
    
    def run(self):
        """Start the Discord bot."""
        print("[FORWARDER] Starting message forwarder...")
        print(f"[FORWARDER] Monitoring webhook messages in destination channels")
        try:
            write_bot_log({"event": "forwarder_start"})
        except Exception:
            pass
        
        self.bot.run(self.token)


if __name__ == "__main__":
    forwarder = MessageForwarder()
    forwarder.run()
