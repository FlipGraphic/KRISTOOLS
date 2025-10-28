import os
import sys
import platform
import asyncio
import time

import discord
from discord.ext import commands

from src.core.config import (
    MENTION_BOT_TOKEN,
    DESTINATION_GUILD_ID,
    VISIBLE_DELAY,
    COOLDOWN_SECONDS,
    PING_CHANNELS,
    _str_to_bool,  # type: ignore
)
from src.core.log_utils import write_bot_log  # bot logs for dashboard

# ===== Config (from .env via config.py) =====
PING_WEBHOOK_ONLY = _str_to_bool(os.getenv("PING_WEBHOOK_ONLY", "false"), False)
cooldowns = {}
locks = {}

# ===== Console Style Setup =====
if platform.system().lower().startswith("win"):
    os.system("color 0a")
print("=====================================================")
print("[START] Mention Bot v2.0 (Universal)")
print("[INFO] Initializing environment...")
print("[INFO] Waiting for Discord connection...")
print("=====================================================\n")
try:
    write_bot_log({"event": "mention_bot_start"})
except Exception:
    pass

# ===== Discord Setup =====
intents = discord.Intents.default()
if hasattr(intents, "message_content"):
    intents.message_content = True
else:
    intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ===== Events =====
@bot.event
async def on_ready():
    print("=====================================================")
    print(f"[LOGIN] Logged in as {bot.user}")
    print(f"[SERVER] Connected to destination server: {DESTINATION_GUILD_ID}")
    print(f"[MODE] Mention Bot Active (Pings @everyone)")
    print(f"[PING_CHANNELS] Monitoring channels: {PING_CHANNELS}")
    print(f"[WEBHOOK_ONLY] {PING_WEBHOOK_ONLY}")
    print("=====================================================\n")
    try:
        write_bot_log({"event": "mention_bot_ready", "user": str(bot.user)})
    except Exception:
        pass
    
    # Validate we're in the correct server
    if DESTINATION_GUILD_ID:
        guild = bot.get_guild(int(DESTINATION_GUILD_ID))
        if not guild:
            print(f"[WARN] Bot not in destination server {DESTINATION_GUILD_ID}")
            print("[WARN] Pings disabled until the bot is invited to that server")
            return
        print(f"[SUCCESS] Connected to server: {guild.name}")
        
        # List the channels we're monitoring
        print(f"[CHANNELS] Monitoring {len(PING_CHANNELS)} channels for @everyone pings:")
        for channel_id in PING_CHANNELS:
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    channel_name = channel.name.encode('ascii', 'replace').decode('ascii')
                    print(f"  [OK] #{channel_name} ({channel_id})")
                except UnicodeEncodeError:
                    print(f"  [OK] Channel-{channel_id} ({channel_id})")
            else:
                print(f"  [ERROR] Channel {channel_id} not found in server")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Only process messages from the destination server (RS Pinger/Notes)
    if not message.guild or str(message.guild.id) != DESTINATION_GUILD_ID:
        return

    # Debug: Log all messages in monitored channels
    if message.channel.id in PING_CHANNELS:
        webhook_status = "webhook" if message.webhook_id else "user"
        try:
            channel_name = message.channel.name.encode('ascii', 'replace').decode('ascii')
            print(f"[DEBUG] Message in #{channel_name} from {webhook_status}: {message.content[:50]}...")
        except UnicodeEncodeError:
            print(f"[DEBUG] Message in Channel-{message.channel.id} from {webhook_status}: {message.content[:50]}...")

    if ((not PING_WEBHOOK_ONLY) or message.webhook_id) and message.channel.id in PING_CHANNELS:
        now = time.time()
        last_ping = cooldowns.get(message.channel.id, 0)
        lock = locks.setdefault(message.channel.id, asyncio.Lock())

        # Check cooldown outside the lock first
        if now - last_ping >= COOLDOWN_SECONDS:
            async with lock:
                # Double-check cooldown inside the lock to prevent race conditions
                current_time = time.time()
                if current_time - cooldowns.get(message.channel.id, 0) < COOLDOWN_SECONDS:
                    try:
                        channel_name = message.channel.name.encode('ascii', 'replace').decode('ascii')
                        print(f"[COOLDOWN] Skipped ping in #{channel_name} (race condition prevented)")
                    except UnicodeEncodeError:
                        print(f"[COOLDOWN] Skipped ping in Channel-{message.channel.id} (race condition prevented)")
                    return

                # Set cooldown BEFORE waiting to prevent double pings
                cooldowns[message.channel.id] = current_time

                try:
                    channel_name = message.channel.name.encode('ascii', 'replace').decode('ascii')
                    print(f"[WAIT] Waiting {VISIBLE_DELAY}s before @everyone in #{channel_name}")
                except UnicodeEncodeError:
                    print(f"[WAIT] Waiting {VISIBLE_DELAY}s before @everyone in Channel-{message.channel.id}")
                
                await asyncio.sleep(VISIBLE_DELAY)

                allowed = discord.AllowedMentions(everyone=True)
                await message.channel.send("@everyone", allowed_mentions=allowed)

                try:
                    channel_name = message.channel.name.encode('ascii', 'replace').decode('ascii')
                    print(f"[PING] Sent @everyone in #{channel_name}")
                except UnicodeEncodeError:
                    print(f"[PING] Sent @everyone in Channel-{message.channel.id}")
                try:
                    write_bot_log({
                        "event": "mention_bot_ping",
                        "dest_channel_id": message.channel.id,
                        "dest_channel_name": message.channel.name,
                    })
                except Exception:
                    pass
        else:
            try:
                channel_name = message.channel.name.encode('ascii', 'replace').decode('ascii')
                print(f"[COOLDOWN] Skipped ping in #{channel_name}")
            except UnicodeEncodeError:
                print(f"[COOLDOWN] Skipped ping in Channel-{message.channel.id}")

    await bot.process_commands(message)

token = (MENTION_BOT_TOKEN or "").strip()
if not token:
    print("[ERROR] MENTION_BOT_TOKEN is not set in tokenkeys.env/.env")
    sys.exit(1)

# ===== Run Bot =====
bot.run(token)
