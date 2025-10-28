# ================= RS Agenda Local Server (with Discord Scheduler) =================
import http.server, socketserver, json, os, threading, time, uuid
import io
import re
import asyncio
import sys
from typing import Dict, List
import requests
from datetime import datetime, timedelta

# -------- Env / Config --------
from dotenv import load_dotenv
load_dotenv("apikeys.env")

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_GUILD_ID  = os.getenv("DISCORD_GUILD_ID", "")
# Forum channel to receive !archive posts (optional)
ARCHIVE_FORUM_ID = os.getenv("ARCHIVE_FORUM_ID", "")
# Category IDs (text channels under these will be grouped)
CAT_DAILY   = os.getenv("CAT_DAILY",   "1313260017989713981")
CAT_INSTORE = os.getenv("CAT_INSTORE", "1400165387001135134")
CAT_UPCOMING= os.getenv("CAT_UPCOMING","1400619782692409404")

# Admin role gating (IDs take precedence over names). CSV supported.
ADMIN_ROLE_IDS   = [r.strip() for r in os.getenv("ADMIN_ROLE_IDS", "").split(",") if r.strip()]
ADMIN_ROLE_NAMES = [r.strip().lower() for r in os.getenv("ADMIN_ROLE_NAMES", "admin,administrator,mods,moderator").split(",") if r.strip()]

PORT   = int(os.getenv("PORT", "8000"))
FOLDER = os.path.dirname(__file__)
os.chdir(FOLDER)

HTTP_TIMEOUT = 12  # seconds

# -------- State --------
STATE_FILE = "agenda_data.json"

# in-memory scheduler store
SCHEDULES: Dict[str, Dict] = {}
SCHED_LOCK = threading.Lock()
SCHED_CONFIGS: Dict[str, Dict] = {}

# Discord bot runtime status
BOT_STATUS = {
    "online": False,
    "username": "",
    "id": "",
    "latency_ms": None,
    "error": "",
}
BOT_THREAD = None
_BOT_STARTED = False


# ================= Helpers =================
def json_ok(**extra):
    return {"ok": True, **extra}

def json_err(msg, **extra):
    return {"ok": False, "error": str(msg), **extra}

def read_body(handler: http.server.BaseHTTPRequestHandler):
    length = int(handler.headers.get("Content-Length", 0) or 0)
    raw = handler.rfile.read(length) if length else b""
    try:
        return json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        return {}

def set_headers(handler, status=200, content_type="application/json"):
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()

def discord_headers():
    if not DISCORD_BOT_TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN missing in apikeys.env")
    return {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}

def _safe_int(x, default=0):
    try:
        return int(str(x))
    except Exception:
        return default

# ================= Optional: Discord Bot (commands) =================
def start_discord_bot():
    global BOT_THREAD, _BOT_STARTED
    if _BOT_STARTED:
        return
    _BOT_STARTED = True

    if not DISCORD_BOT_TOKEN:
        BOT_STATUS.update({"online": False, "error": "No DISCORD_BOT_TOKEN set"})
        return

    def _worker():
        try:
            try:
                import discord
                from discord.ext import commands
            except Exception as e:
                BOT_STATUS.update({"online": False, "error": f"discord.py missing: {e}"})
                return

            intents = discord.Intents.default()
            intents.guilds = True
            intents.messages = True
            intents.message_content = True  # requires privileged intent enabled

            bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

            # ---------- Embed helpers ----------
            def make_embed(title: str = None, description: str = None, color: int = 0x5865F2):
                e = discord.Embed(title=title or None, description=description or None, colour=color)
                try:
                    e.timestamp = datetime.utcnow()
                except Exception:
                    pass
                e.set_footer(text="RS Agenda Bot")
                return e

            async def reply_embed(ctx: commands.Context, description: str, title: str = None, color: int = 0x5865F2):
                try:
                    emb = make_embed(title=title, description=description, color=color)
                    return await ctx.reply(embed=emb)
                except Exception:
                    return await ctx.reply(description)

            def channel_from_token(guild: discord.Guild, token: str):
                """Resolve a channel from mention <#id>, raw id, or name. Returns (channel, id_str)."""
                if not token:
                    return None, ""
                t = token.strip()
                # <#123>
                m = re.match(r"^<#(\d+)>$", t)
                if m:
                    cid = int(m.group(1))
                    ch = guild.get_channel(cid)
                    return ch, str(cid)
                # raw id
                if t.isdigit():
                    cid = int(t)
                    ch = guild.get_channel(cid)
                    return ch, str(cid)
                # by name (first match)
                try:
                    for ch in guild.text_channels:
                        if str(ch.name).lower() == t.lower():
                            return ch, str(ch.id)
                except Exception:
                    pass
                return None, ""

            @bot.event
            async def on_ready():
                try:
                    me = bot.user
                    BOT_STATUS.update({
                        "online": True,
                        "username": getattr(me, "name", ""),
                        "id": str(getattr(me, "id", "")),
                        "latency_ms": int(getattr(bot, "latency", 0) * 1000),
                        "error": "",
                    })
                    await bot.change_presence(activity=discord.Game(name="RS Agenda"))
                except Exception as e:
                    BOT_STATUS.update({"online": True, "error": str(e)[:200]})

            def _is_same_guild(ctx):
                try:
                    gid = _safe_int(DISCORD_GUILD_ID)
                    return ctx.guild and ctx.guild.id == gid if gid else True
                except Exception:
                    return True

            def _mod_only(ctx):
                m = ctx.author
                # First: role ID allowlist
                try:
                    member_roles = getattr(m, "roles", []) or []
                    if ADMIN_ROLE_IDS:
                        for role in member_roles:
                            rid = str(getattr(role, "id", ""))
                            if rid and rid in ADMIN_ROLE_IDS:
                                return True
                    # Second: role name allowlist (case-insensitive)
                    if ADMIN_ROLE_NAMES:
                        for role in member_roles:
                            rname = str(getattr(role, "name", "")).strip().lower()
                            if rname and rname in ADMIN_ROLE_NAMES:
                                return True
                except Exception:
                    pass
                # Fallback: built-in admin permission
                perms = getattr(getattr(m, "guild_permissions", None), "administrator", False)
                return bool(perms)

            def _cat_from_key(guild, key: str):
                key = (key or "").strip().lower()
                cat_id = None
                if key in ("daily", "d"):
                    cat_id = _safe_int(CAT_DAILY)
                elif key in ("instore", "store", "i"):
                    cat_id = _safe_int(CAT_INSTORE)
                elif key in ("upcoming", "up", "u"):
                    cat_id = _safe_int(CAT_UPCOMING)
                if not cat_id:
                    return None
                return discord.utils.get(guild.categories, id=cat_id)

            @bot.command(name="help", aliases=["commands"])
            async def _help(ctx: commands.Context):
                if not _is_same_guild(ctx):
                    return
                now = datetime.now().astimezone()
                off = now.utcoffset() or timedelta(0)
                sign = "+" if off.total_seconds() >= 0 else "-"
                secs = int(abs(off.total_seconds()))
                oh, om = secs // 3600, (secs % 3600) // 60
                tzline = f"{now.tzname() or 'local'} (UTC{sign}{oh:02d}:{om:02d})"
                desc = (
                    "Commands (admin)\n"
                    "• !make <daily|instore|upcoming> <name>\n"
                    f"• !setdrop YYYY-MM-DD HH:MM [#channel|id|name] — server TZ {tzline}\n"
                    "• !setdrop list | !setdrop remove <id>\n"
                    "• !setreminder <minutes> <@&role|none> <message>\n"
                    "• !setlive <message>\n"
                    "• !schedule\n"
                    "• !tz\n\n"
                    "Mods only: !delete, !transfer <daily|instore|upcoming>, !archive"
                )
                await ctx.send(embed=make_embed(title="RS Agenda Commands", description=desc))

            @bot.command(name="delete")
            async def _delete(ctx: commands.Context):
                if not _is_same_guild(ctx):
                    return
                if not _mod_only(ctx):
                    return await reply_embed(ctx, "❌ Need Manage Channels permission.", title="Permission denied", color=0xED4245)
                ch = ctx.channel
                name = getattr(ch, "name", "this channel")
                await ctx.send(embed=make_embed(title="Delete", description=f"Deleting #{name}…", color=0xED4245))
                try:
                    await ch.delete(reason=f"Requested by {ctx.author}")
                except Exception as e:
                    await ctx.send(embed=make_embed(title="Delete failed", description=str(e), color=0xED4245))

            @bot.command(name="transfer")
            async def _transfer(ctx: commands.Context, target: str = ""):
                if not _is_same_guild(ctx):
                    return
                if not _mod_only(ctx):
                    return await reply_embed(ctx, "❌ Need Manage Channels permission.", title="Permission denied", color=0xED4245)
                if not target:
                    return await reply_embed(ctx, "Usage: !transfer <daily|instore|upcoming>", title="Transfer")
                try:
                    cat = _cat_from_key(ctx.guild, target)
                    if not cat:
                        return await reply_embed(ctx, "❌ Unknown category. Use daily|instore|upcoming", title="Transfer", color=0xED4245)
                    await ctx.channel.edit(category=cat, sync_permissions=True, reason=f"Transfer by {ctx.author}")
                    await ctx.send(embed=make_embed(title="Transfer", description=f"✅ Moved to #{cat.name} (permissions synced)", color=0x57F287))
                except Exception as e:
                    await ctx.send(embed=make_embed(title="Transfer failed", description=str(e), color=0xED4245))

            @bot.command(name="archive")
            async def _archive(ctx: commands.Context):
                """Archive the entire channel into a Forum post and delete the channel.
                - Uses ARCHIVE_FORUM_ID from apikeys.env
                - Attaches a full text transcript (oldest → newest)
                - Posts image attachment URLs in batches for preview
                """
                if not _is_same_guild(ctx):
                    return
                if not _mod_only(ctx):
                    return await ctx.reply("❌ Need Manage Channels permission.")
                try:
                    if not ARCHIVE_FORUM_ID:
                        return await ctx.reply("❌ Set ARCHIVE_FORUM_ID in apikeys.env to a Forum channel ID.")

                    forum_id = int(ARCHIVE_FORUM_ID)
                    forum = ctx.guild.get_channel(forum_id) or await ctx.guild.fetch_channel(forum_id)
                    if forum is None:
                        return await ctx.reply("❌ ARCHIVE_FORUM_ID not found in this guild.")

                    # Optional: ask for a forum tag
                    applied_tags = None
                    try:
                        tags = getattr(forum, "available_tags", []) or []
                        if tags:
                            tag_list = "\n".join([f"{i+1}. {t.name}" for i, t in enumerate(tags)])
                            prompt = await ctx.reply(
                                ("Select a tag for the archive post (type number or name), or type 'skip':\n" + tag_list)[:1900]
                            )
                            def check(m):
                                return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
                            try:
                                reply = await bot.wait_for('message', timeout=60.0, check=check)
                                choice = (reply.content or "").strip()
                                if choice.lower() != 'skip':
                                    idx = None
                                    try:
                                        idx = int(choice) - 1
                                    except Exception:
                                        idx = None
                                    sel = None
                                    if idx is not None and 0 <= idx < len(tags):
                                        sel = tags[idx]
                                    else:
                                        for t in tags:
                                            if t.name.lower() == choice.lower():
                                                sel = t; break
                                    if sel:
                                        applied_tags = [sel]
                            except Exception:
                                pass
                            try:
                                await prompt.delete()
                                if 'reply' in locals():
                                    await reply.delete()
                            except Exception:
                                pass
                    except Exception:
                        applied_tags = None

                    created_at = time.strftime("%Y-%m-%d %H:%M:%S")
                    header = (f"Archive of #{ctx.channel.name} — by {ctx.author.mention} on {created_at}\n"
                              f"Source channel id: {ctx.channel.id}")

                    # Create a new forum post (thread)
                    try:
                        thread_tuple = await forum.create_thread(name=ctx.channel.name, content=header, applied_tags=applied_tags)
                    except TypeError:
                        # older discord.py may not accept applied_tags
                        thread_tuple = await forum.create_thread(name=ctx.channel.name, content=header)
                    try:
                        thread = thread_tuple[0]
                    except Exception:
                        thread = thread_tuple  # older versions may return Thread directly

                    # Build transcript and collect image URLs
                    lines = []
                    image_urls = []
                    async for m in ctx.channel.history(limit=None, oldest_first=True):
                        ts = m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else ""
                        author = getattr(m.author, "display_name", getattr(m.author, "name", "user"))
                        content = (m.content or "").replace("\r\n", "\n").replace("\r", "\n")
                        base = f"[{ts}] {author}: {content}".strip()
                        attach_lines = []
                        for a in getattr(m, "attachments", []) or []:
                            url = getattr(a, "url", None)
                            if url:
                                attach_lines.append(f"[attachment] {url}")
                                ct = (getattr(a, "content_type", "") or "").lower()
                                fn = (getattr(a, "filename", "") or "").lower()
                                if ct.startswith("image/") or fn.endswith((".png",".jpg",".jpeg",".gif",".webp")):
                                    image_urls.append(url)
                        full = base if not attach_lines else (base + ("\n" + "\n".join(attach_lines) if base else "\n".join(attach_lines)))
                        if full:
                            lines.append(full)

                    transcript = "\n".join(lines) if lines else "(no messages)"
                    fp = io.BytesIO(transcript.encode("utf-8"))
                    await thread.send(content="Transcript attached:", file=discord.File(fp, filename=f"archive-#{ctx.channel.name}.txt"))

                    # Post image URLs in batches so Discord previews them
                    if image_urls:
                        B = 10
                        total = (len(image_urls) + B - 1) // B
                        for i in range(0, len(image_urls), B):
                            part = image_urls[i:i+B]
                            await thread.send(content=f"Images ({i//B + 1}/{total}):\n" + "\n".join(part))

                    await ctx.message.add_reaction("✅")
                    await ctx.send(f"📦 Archived to forum post: {thread.mention}. Deleting source…")

                    try:
                        await ctx.channel.delete(reason=f"Archived to forum post {getattr(thread,'id','')} ")
                    except Exception as de:
                        await thread.send(f"⚠️ Auto-delete failed: {de}")
                except Exception as e:
                    await ctx.send(f"❌ Archive failed: {e}")

            # ===== Quick channel + scheduler helpers =====
            @bot.command(name="make")
            async def _make(ctx: commands.Context, target: str = "", *, name: str = ""):
                if not _is_same_guild(ctx):
                    return
                if not _mod_only(ctx):
                    return await ctx.reply("❌ Need Manage Channels permission.")
                target = (target or "").strip().lower()
                if target not in ("daily", "instore", "upcoming"):
                    return await ctx.reply("Usage: !make <daily|instore|upcoming> <channel-name>")
                if not name:
                    return await ctx.reply("Provide a channel name.")
                cat = _cat_from_key(ctx.guild, target)
                if not cat:
                    return await ctx.reply("❌ Category not found; check CAT_* env IDs.")
                ch = await ctx.guild.create_text_channel(name=name, category=cat, reason=f"Created by {ctx.author}")
                await ch.edit(sync_permissions=True)
                await ctx.reply(f"✅ Created {ch.mention} in #{cat.name}")

            @bot.command(name="setdrop")
            async def _setdrop(ctx: commands.Context, *args):
                """Set/list/remove drop configs.
                Syntax:
                  !setdrop YYYY-MM-DD HH:MM [#channel|id|name]
                  !setdrop list
                  !setdrop remove <id>
                """
                if not _is_same_guild(ctx):
                    return
                if not _mod_only(ctx):
                    return await reply_embed(ctx, "❌ Need Manage Channels permission.", title="setdrop", color=0xED4245)

                # list pending configs
                if len(args) >= 1 and str(args[0]).lower() in ("list", "ls"):
                    items = list(SCHED_CONFIGS.items())
                    if not items:
                        return await reply_embed(ctx, "No pending drops. Use: !setdrop YYYY-MM-DD HH:MM [#channel]", title="setdrop")
                    lines = []
                    for idx, (ch_id, cfg) in enumerate(items, start=1):
                        ch = ctx.guild.get_channel(int(ch_id))
                        name = f"#{getattr(ch, 'name', ch_id)}"
                        when = cfg.get("drop_ts_ms")
                        if when:
                            when_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(when/1000))
                        else:
                            when_str = "(no time)"
                        lines.append(f"drop{idx} — {name} — {when_str}")
                    return await ctx.send(embed=make_embed(title="Pending Drops", description="\n".join(lines)))

                # remove by id index
                if len(args) >= 1 and str(args[0]).lower() in ("remove", "rm", "delete"):
                    if len(args) < 2:
                        return await reply_embed(ctx, "Usage: !setdrop remove <id>\nTip: run !setdrop list to see ids like drop1, drop2…", title="setdrop remove")
                    target = str(args[1]).lower().lstrip("drop")
                    try:
                        idx = int(target)
                    except Exception:
                        return await reply_embed(ctx, "Invalid id. Example: !setdrop remove drop1", title="setdrop remove", color=0xED4245)
                    items = list(SCHED_CONFIGS.items())
                    if not (1 <= idx <= len(items)):
                        return await reply_embed(ctx, "Id out of range.", title="setdrop remove", color=0xED4245)
                    ch_id, _ = items[idx-1]
                    SCHED_CONFIGS.pop(ch_id, None)
                    ch = ctx.guild.get_channel(int(ch_id))
                    name = f"#{getattr(ch, 'name', ch_id)}"
                    return await reply_embed(ctx, f"Removed {name} from pending drops.", title="setdrop remove", color=0x57F287)

                # set drop time for a (possibly different) channel
                if not args or len(args) < 2:
                    now = datetime.now().astimezone()
                    off = now.utcoffset() or timedelta(0)
                    sign = "+" if off.total_seconds() >= 0 else "-"
                    secs = int(abs(off.total_seconds()))
                    oh, om = secs // 3600, (secs % 3600) // 60
                    tzline = f"{now.tzname() or 'local'} (UTC{sign}{oh:02d}:{om:02d})"
                    return await reply_embed(ctx, f"Usage: !setdrop YYYY-MM-DD HH:MM [#channel|id|name]\nTimes use server timezone {tzline}.", title="setdrop")

                # Parse datetime
                date_tok = str(args[0])
                time_tok = None
                chan_tok = None
                if len(args) >= 2:
                    # If second token looks like time HH:MM, use it; otherwise treat as channel
                    if re.match(r"^\d{2}:\d{2}$", str(args[1])):
                        time_tok = str(args[1])
                        chan_tok = " ".join(args[2:]) if len(args) > 2 else None
                    else:
                        time_tok = None
                        chan_tok = " ".join(args[1:])
                try:
                    if time_tok:
                        naive = datetime.strptime(f"{date_tok} {time_tok}", "%Y-%m-%d %H:%M")
                    else:
                        # Accept compact form YYYY-MM-DDTHH:MM or YYYY-MM-DD_HH:MM
                        m = re.match(r"^(\d{4}-\d{2}-\d{2})[T_](\d{2}:\d{2})$", date_tok)
                        if not m:
                            raise ValueError("bad ts")
                        naive = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M")
                    local_tz = datetime.now().astimezone().tzinfo
                    dt_local = naive.replace(tzinfo=local_tz)
                    drop_ms = int(dt_local.timestamp() * 1000)
                except Exception:
                    return await reply_embed(ctx, "❌ Invalid datetime. Use YYYY-MM-DD HH:MM", title="setdrop", color=0xED4245)

                # Resolve channel (defaults to current channel)
                ch = None
                ch_id_str = None
                if chan_tok:
                    ch, ch_id_str = channel_from_token(ctx.guild, chan_tok)
                if not ch:
                    ch = ctx.channel
                    ch_id_str = str(ctx.channel.id)

                key = ch_id_str
                cfg = SCHED_CONFIGS.get(key) or {"reminders": [], "msgLive": ""}
                cfg["drop_ts_ms"] = drop_ms
                SCHED_CONFIGS[key] = cfg
                off = dt_local.utcoffset() or timedelta(0)
                sign = "+" if off.total_seconds() >= 0 else "-"
                secs = int(abs(off.total_seconds()))
                oh, om = secs // 3600, (secs % 3600) // 60
                when = dt_local.strftime("%Y-%m-%d %H:%M")
                desc = (
                    f"Channel: {ch.mention}\n"
                    f"Drop time: {when} {dt_local.tzname() or ''} (UTC{sign}{oh:02d}:{om:02d})\n"
                    "Next: add reminders with !setreminder <minutes> <@&role|none> <message> or set LIVE with !setlive <message>"
                )
                await ctx.send(embed=make_embed(title="Drop time set", description=desc, color=0x57F287))

            @bot.command(name="setreminder")
            async def _setreminder(ctx: commands.Context, minutes: int = None, role: str = None, *, msg: str = ""):
                if not _is_same_guild(ctx):
                    return
                if not _mod_only(ctx):
                    return await reply_embed(ctx, "❌ Need Manage Channels permission.", title="setreminder", color=0xED4245)
                if minutes is None:
                    return await reply_embed(ctx, "Usage: !setreminder <minutes> <@&role|none> <message>", title="setreminder")
                role_id = ""
                if ctx.message.role_mentions:
                    role_id = str(ctx.message.role_mentions[0].id)
                elif (role or "").lower() != "none":
                    # try parse raw id
                    rid = (role or "").strip("<@&>")
                    if rid.isdigit():
                        role_id = rid
                def with_role(rid: str, text: str) -> str:
                    return (f"<@&{rid}> {text}".strip() if rid else (text or "")).strip()
                def compose(offset_min: int, content: str, rid: str) -> str:
                    head = f"{offset_min} mins Reminder" + (f" <@&{rid}>" if rid else "")
                    clean = (content or "").strip()
                    return f"{clean}\n- # {head}" if clean else f"### {head}"
                key = str(ctx.channel.id)
                cfg = SCHED_CONFIGS.get(key) or {"reminders": [], "msgLive": ""}
                cfg.setdefault("reminders", [])
                cfg["reminders"].append({
                    "offset_min": max(0, int(minutes)),
                    "label": f"T-{max(0, int(minutes))}",
                    "content": compose(max(0, int(minutes)), msg, role_id)
                })
                SCHED_CONFIGS[key] = cfg
                await reply_embed(ctx, f"Reminder added (T-{minutes}). Add more or set live: !setlive <message>", title="setreminder", color=0x57F287)

            @bot.command(name="setlive")
            async def _setlive(ctx: commands.Context, *, msg: str = ""):
                if not _is_same_guild(ctx):
                    return
                if not _mod_only(ctx):
                    return await reply_embed(ctx, "❌ Need Manage Channels permission.", title="setlive", color=0xED4245)
                if not msg:
                    return await reply_embed(ctx, "Usage: !setlive <message>", title="setlive")
                key = str(ctx.channel.id)
                cfg = SCHED_CONFIGS.get(key) or {"reminders": []}
                cfg["msgLive"] = msg
                SCHED_CONFIGS[key] = cfg
                await reply_embed(ctx, "LIVE message set. Start schedule with !schedule", title="setlive", color=0x57F287)

            @bot.command(name="schedule")
            async def _schedule_cmd(ctx: commands.Context):
                if not _is_same_guild(ctx):
                    return
                if not _mod_only(ctx):
                    return await reply_embed(ctx, "❌ Need Manage Channels permission.", title="schedule", color=0xED4245)
                key = str(ctx.channel.id)
                cfg = SCHED_CONFIGS.get(key)
                if not cfg or not cfg.get("drop_ts_ms") or not cfg.get("msgLive"):
                    return await reply_embed(ctx, "Incomplete. Use !setdrop … then !setreminder … and !setlive …", title="schedule", color=0xED4245)
                drop_ms = int(cfg["drop_ts_ms"])
                reminders = cfg.get("reminders", [])
                msg_live = cfg.get("msgLive", "")
                sched_id, etas, err = schedule_drop_custom(str(ctx.channel.id), drop_ms, reminders, msg_live)
                if err:
                    return await reply_embed(ctx, err, title="schedule", color=0xED4245)
                SCHED_CONFIGS.pop(key, None)
                lines = [f"{e['label']} → {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(e['eta_ms']/1000))}" for e in etas]
                await ctx.send(embed=make_embed(title="Scheduled", description=("\n".join(lines) or "(all in past)"), color=0x57F287))

            @bot.command(name="tz")
            async def _tz(ctx: commands.Context):
                if not _is_same_guild(ctx):
                    return
                now = datetime.now().astimezone()
                off = now.utcoffset() or timedelta(0)
                sign = "+" if off.total_seconds() >= 0 else "-"
                secs = int(abs(off.total_seconds()))
                oh, om = secs // 3600, (secs % 3600) // 60
                await ctx.send(embed=make_embed(title="Server time", description=(
                    f"{now.strftime('%Y-%m-%d %H:%M:%S')} {now.tzname() or 'local'} (UTC{sign}{oh:02d}:{om:02d})\n"
                    "!setdrop interprets dates in this timezone."
                )))
            # Run bot (blocking in this thread)
            bot.run(DISCORD_BOT_TOKEN)
        except Exception as e:
            BOT_STATUS.update({"online": False, "error": str(e)[:200]})

    BOT_THREAD = threading.Thread(target=_worker, name="discord-bot", daemon=True)
    BOT_THREAD.start()

def send_discord_message(channel_id: str, content: str) -> dict:
    """
    Fire-and-forget message send to Discord channel.
    Returns JSON {id, content, ...} on success or {'error': ...} on failure.
    """
    if not channel_id or not content:
        return {"error": "channel_id and content required"}
    if not DISCORD_BOT_TOKEN:
        return {"error": "Bot token missing"}

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    payload = {"content": content}
    try:
        r = requests.post(url, headers=discord_headers(), json=payload, timeout=HTTP_TIMEOUT)
        if r.status_code == 200 or r.status_code == 201:
            return r.json()
        return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
    except requests.RequestException as e:
        return {"error": str(e)}

def fetch_guild_channels():
    if not DISCORD_BOT_TOKEN or not DISCORD_GUILD_ID:
        raise RuntimeError("Missing DISCORD_BOT_TOKEN or DISCORD_GUILD_ID in apikeys.env")
    url = f"https://discord.com/api/v10/guilds/{DISCORD_GUILD_ID}/channels"
    r = requests.get(url, headers=discord_headers(), timeout=HTTP_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"Discord API error {r.status_code}: {r.text[:200]}")
    return r.json()

def categorize_channels(all_channels):
    # type 0 = text channels
    daily, instore, upcoming = [], [], []

    # Preserve existing notes
    existing = {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            cur = json.load(f)
        for k in ("daily", "instore", "upcoming"):
            for ch in cur.get(k, []):
                existing[str(ch.get("id"))] = ch.get("notes", "")
    except Exception:
        pass

    for ch in all_channels:
        if str(ch.get("type")) != "0":
            continue
        pid = str(ch.get("parent_id") or "")
        item = {
            "id": str(ch.get("id")),
            "name": ch.get("name") or "",
            "notes": existing.get(str(ch.get("id")), "")
        }
        if pid == str(CAT_DAILY):
            daily.append(item)
        elif pid == str(CAT_INSTORE):
            instore.append(item)
        elif pid == str(CAT_UPCOMING):
            upcoming.append(item)
    return {"daily": daily, "instore": instore, "upcoming": upcoming}

def autosave_state(new_chunks):
    current = {"daily": [], "instore": [], "upcoming": [], "optional": [], "output": ""}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            current.update(obj)
    except Exception:
        pass
    current["daily"]   = new_chunks.get("daily", [])
    current["instore"] = new_chunks.get("instore", [])
    current["upcoming"]= new_chunks.get("upcoming", [])
    current["optional"]= new_chunks.get("optional", [])
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
    return current

# ---- Scheduler helpers ----
def _schedule_one(eta_ms: int, label: str, channel_id: str, content: str, sched_id: str):
    """
    Create a timer to send at eta_ms (epoch ms). If eta already passed, return None.
    """
    now_ms = int(time.time() * 1000)
    delay = (eta_ms - now_ms) / 1000.0
    if delay <= 0:
        return None

    def task():
        res = send_discord_message(channel_id, content)
        # log to console (no emojis)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        if "error" in res:
            print(f"[{stamp}] scheduler {sched_id} • {label} • send ERR: {res['error']}")
        else:
            print(f"[{stamp}] scheduler {sched_id} • {label} • sent msg_id={res.get('id')}")

    t = threading.Timer(delay, task)
    t.daemon = True
    t.start()
    return t

def schedule_drop(channel_id: str, drop_ts_ms: int, msg30: str, msg15: str, msg_live: str):
    """
    DEPRECATED: Use schedule_drop_custom() instead for more flexibility.
    
    Create up to three timers: T-30min, T-15min, T-0min.
    Only future ones will be scheduled. Returns (sched_id, etas[])
    """
    if not channel_id:
        return None, [], "channel_id required"
    if not drop_ts_ms or drop_ts_ms <= 0:
        return None, [], "drop_ts_ms required"
    if not msg_live:
        return None, [], "msgLive required"

    # Compute targets in ms
    M = 60 * 1000
    schedule_points = []
    if msg30:
        schedule_points.append(("T-30", drop_ts_ms - 30 * M, msg30))
    if msg15:
        schedule_points.append(("T-15", drop_ts_ms - 15 * M, msg15))
    schedule_points.append(("LIVE", drop_ts_ms, msg_live))

    timers = []
    etas: List[dict] = []
    sched_id = uuid.uuid4().hex

    for label, eta_ms, content in schedule_points:
        t = _schedule_one(eta_ms, label, channel_id, content, sched_id)
        etas.append({"label": label, "eta_ms": int(eta_ms), "scheduled": bool(t)})
        if t:
            timers.append(t)

    with SCHED_LOCK:
        SCHEDULES[sched_id] = {
            "channel_id": channel_id,
            "drop_ts_ms": drop_ts_ms,
            "timers": timers,
            "messages": {"msg30": msg30, "msg15": msg15, "msgLive": msg_live},
            "created_ms": int(time.time() * 1000),
        }

    return sched_id, etas, None

def schedule_drop_custom(channel_id: str, drop_ts_ms: int, reminders: List[dict], msg_live: str):
    """
    reminders: [{"label":"T-30","offset_min":30,"content":"..."}, ...]
    - offset_min is minutes BEFORE drop (positive number). For at-drop, use 0.
    - content may be blank to generate default header.
    Returns (id, etas[], err)
    """
    if not channel_id:
        return None, [], "channel_id required"
    if not drop_ts_ms or drop_ts_ms <= 0:
        return None, [], "drop_ts_ms required"
    if not msg_live:
        return None, [], "msgLive required"

    # Always include LIVE at T-0
    schedule_points = [("LIVE", drop_ts_ms, msg_live)]
    M = 60 * 1000
    for r in reminders or []:
        try:
            off_min = int(r.get("offset_min", 0))
        except Exception:
            off_min = 0
        label = str(r.get("label") or f"T-{off_min}")
        content = str(r.get("content") or "").strip()
        eta = drop_ts_ms - max(0, off_min) * M
        schedule_points.append((label, eta, content))

    timers = []
    etas: List[dict] = []
    sched_id = uuid.uuid4().hex

    for label, eta_ms, content in schedule_points:
        t = _schedule_one(eta_ms, label, channel_id, content or label, sched_id)
        etas.append({"label": label, "eta_ms": int(eta_ms), "scheduled": bool(t)})
        if t:
            timers.append(t)

    with SCHED_LOCK:
        SCHEDULES[sched_id] = {
            "channel_id": channel_id,
            "drop_ts_ms": drop_ts_ms,
            "timers": timers,
            "messages": {"reminders": reminders, "msgLive": msg_live},
            "created_ms": int(time.time() * 1000),
        }

    return sched_id, etas, None

def cancel_schedule(sched_id: str):
    with SCHED_LOCK:
        obj = SCHEDULES.pop(sched_id, None)
    if not obj:
        return False
    for t in obj.get("timers", []):
        try:
            t.cancel()
        except Exception:
            pass
    return True


# ================= HTTP Handler =================
class Handler(http.server.SimpleHTTPRequestHandler):
    def _ok(self, payload, status=200, content_type="application/json"):
        set_headers(self, status, content_type)
        if content_type == "application/json":
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        else:
            # payload should already be bytes for non-JSON
            self.wfile.write(payload)

    def do_OPTIONS(self):
        set_headers(self)

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/health":
            info = {
                "status": "ok",
                "have_discord_token": bool(DISCORD_BOT_TOKEN),
                "guild": DISCORD_GUILD_ID or "",
                "port": PORT,
                "bot": BOT_STATUS,
            }
            return self._ok(info)

        elif path == "/load_settings":
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    obj = json.load(f)  # read as dict so _ok can json.dumps it
                return self._ok(obj)
            except FileNotFoundError:
                return self._ok({})

        elif path in ("/discord_health", "/discord-health"):
            try:
                fetch_guild_channels()
                data = {"status": "ok", "bot": BOT_STATUS}
                return self._ok(data)
            except Exception as e:
                data = json_err(str(e))
                data["bot"] = BOT_STATUS
                return self._ok(data, status=503)

        # Fall back to static file serving (Daily.html, css/js, etc.)
        return super().do_GET()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        data = read_body(self)

        # --- Settings ---
        if path == "/save_settings":
            try:
                with open(STATE_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return self._ok(json_ok(saved=True))
            except Exception as e:
                return self._ok(json_err(e), status=500)

        # --- Discord: fetch channels & auto-save grouped lists ---
        if path == "/fetch_channels":
            try:
                channels = fetch_guild_channels()
                categorized = categorize_channels(channels)
                autosave_state(categorized)
                return self._ok(json_ok(**categorized))
            except Exception as e:
                return self._ok(json_err(e), status=500)

        # --- Discord: send message now ---
        if path == "/discord/send_message":
            channel_id = str(data.get("channel_id", "")).strip()
            content    = str(data.get("content", "")).strip()
            res = send_discord_message(channel_id, content)
            if "error" in res:
                return self._ok(json_err(res["error"]), status=500)
            return self._ok(json_ok(id=res.get("id"), content=res.get("content")))

        # --- Scheduler: schedule drop (supports custom reminders) ---
        if path == "/scheduler/schedule_drop":
            channel_id = str(data.get("channel_id", "")).strip()
            drop_ts_ms = int(data.get("drop_ts_ms") or 0)
            msgLive= str(data.get("msgLive", "") or "").strip()

            reminders = data.get("reminders")
            if isinstance(reminders, list) and reminders:
                sched_id, etas, err = schedule_drop_custom(channel_id, drop_ts_ms, reminders, msgLive)
            else:
                # backward compatibility with msg30/msg15 fields
                msg30  = str(data.get("msg30", "") or "").strip()
                msg15  = str(data.get("msg15", "") or "").strip()
                sched_id, etas, err = schedule_drop(channel_id, drop_ts_ms, msg30, msg15, msgLive)
            if err:
                return self._ok(json_err(err), status=400)
            return self._ok(json_ok(id=sched_id, etas=etas))

        # --- Scheduler: cancel ---
        if path == "/scheduler/cancel":
            sched_id = str(data.get("id", "")).strip()
            if not sched_id:
                return self._ok(json_err("id required"), status=400)
            ok = cancel_schedule(sched_id)
            if not ok:
                return self._ok(json_err("not found"), status=404)
            return self._ok(json_ok(cancelled=True))

        # --- Amazon passthrough (not used here) ---
        if path in ("/price", "/search"):
            return self._ok(json_err("Amazon API not connected to this server"), status=501)

        # Not found
        return self._ok(json_err("Not found"), status=404)

# ================= END HTTP Handler =================

# ================= Server Runner =================
class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

def run_server():
    with ThreadingHTTPServer(("", PORT), Handler) as httpd:
        print(f"RS Agenda Local Server running at http://127.0.0.1:{PORT}")
        print("Endpoints:")
        print("  GET  /health")
        print("  GET  /load_settings")
        print("  POST /save_settings")
        print("  POST /fetch_channels")
        print("  GET  /discord_health  (alias: /discord-health)")
        print("  POST /discord/send_message")
        print("  POST /scheduler/schedule_drop")
        print("  POST /scheduler/cancel")
        print("Press CTRL+C to stop.")
        httpd.serve_forever()


# ================= Entry Point =================
if __name__ == "__main__":
    # Start Discord bot (non-blocking) if token present
    try:
        start_discord_bot()
    except Exception as _e:
        BOT_STATUS.update({"online": False, "error": str(_e)[:200]})
    run_server()
