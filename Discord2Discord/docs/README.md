# Discord2Discord Bridge Suite

A comprehensive Discord message forwarding and filtering system that bridges messages between Discord servers with intelligent classification and automated notifications.

## Features

- **Message Forwarding**: Bridge messages from source channels to destination channels via webhooks
- **Intelligent Filtering**: Automatically classify messages (Amazon, Mavely, Upcoming, Default)
- **Mention Bot**: Automated @everyone pings with cooldown management
- **Web Dashboard**: Real-time monitoring and management interface
- **Duplicate Prevention**: Smart filtering to prevent spam and duplicates

## Project Structure

```
Discord2Discord/
├── src/                    # Python source files
│   ├── bots/              # Discord bot implementations
│   │   ├── d2d.py        # Main bridge bot (discum-based)
│   │   ├── mention_bot.py # @everyone pinger bot
│   │   └── message_forwarder.py # Message classifier and forwarder
│   ├── core/              # Core functionality
│   │   ├── config.py     # Configuration management
│   │   ├── filterbot.py  # Message classification logic
│   │   └── log_utils.py   # Centralized logging utilities
│   └── web/               # Web interface
│       ├── http_server.py # HTTP server for dashboard
│       ├── dashboard.html # Main dashboard interface
│       └── shutdown_bots.py # Bot shutdown utilities
├── config/                 # Configuration files
│   ├── tokenkeys.env      # API tokens and settings
│   └── channel_map.json   # Source channel to webhook mapping
├── logs/                   # Runtime logs (gitignored)
│   ├── botlogs.json       # Bot status and events
│   ├── d2dlogs.json       # Bridge forwarding logs
│   └── filteredlogs.json  # Classification and filtering logs
├── scripts/                # Launcher scripts
│   ├── launcher.py        # Main Python launcher
│   ├── run_forwarder.bat   # Windows batch launcher
│   ├── run.sh             # Linux/Mac shell launcher
│   ├── RUN.vbs            # Windows silent launcher
│   ├── SHUTDOWN.bat       # Windows shutdown script
│   └── SHUTDOWN.ps1       # PowerShell shutdown script
├── docs/                   # Documentation
│   ├── README.md          # This file
│   ├── COMPLETION_SUMMARY.md
│   ├── DASHBOARD_FIXES.md
│   ├── SHUTDOWN_FEATURE.md
│   └── SYSTEM_UPDATES.md
└── requirements.txt        # Python dependencies
```

## Message Flow

1. **Source Message**: User posts in monitored source channel
2. **Bridge Detection**: `d2d.py` receives message via discum
3. **Webhook Forward**: Message forwarded to destination via webhook
4. **Classification**: Message analyzed by `filterbot.py`
5. **Smart Forwarding**: `message_forwarder.py` sends to appropriate channel
6. **Notification**: `mention_bot.py` sends @everyone ping (if configured)

## Quick Start

1. **Install Dependencies**:
```bash
pip install -r requirements.txt
```

2. **Configure Environment**:
   - Copy `config/tokenkeys.env.example` to `config/tokenkeys.env`
   - Fill in your Discord tokens and channel IDs

3. **Set Up Channel Mapping**:
   - Edit `config/channel_map.json` to map source channels to webhook URLs

4. **Run the System**:
   - **Windows**: Double-click `scripts/RUN.vbs` (silent) or `scripts/run_forwarder.bat`
   - **Linux/Mac**: Run `scripts/run.sh`
   - **Manual**: Run `python scripts/launcher.py`

5. **Access Dashboard**:
   - Open http://localhost:8080/dashboard.html

## Configuration

### Environment Variables (tokenkeys.env)

#### Required Tokens
- `DISCORD_TOKEN` - User token for d2d.py (discum self-bot)
- `MENTION_BOT_TOKEN` - Bot token for message_forwarder.py and mention_bot.py

#### Server Configuration
- `SOURCE_GUILD_ID` - Source server where messages originate
- `DESTINATION_GUILD_ID` - Destination server where messages go

#### Smart Forwarding Channels
- `SMART_AMAZON_CHANNEL_ID` - Channel for Amazon links
- `SMART_MAVELY_CHANNEL_ID` - Channel for Mavely/affiliate links
- `SMART_UPCOMING_CHANNEL_ID` - Channel for time-sensitive events
- `SMART_DEFAULT_CHANNEL_ID` - Fallback channel

#### Mention Bot Settings
- `PING_CHANNELS` - Comma-separated channel IDs for @everyone pings
- `VISIBLE_DELAY` - Seconds to wait before sending @everyone
- `COOLDOWN_SECONDS` - Cooldown between pings per channel
- `PING_WEBHOOK_ONLY` - Only ping for webhook messages

### Channel Mapping (channel_map.json)

```json
{
  "1390535329575866368": "https://discord.com/api/webhooks/...",
  "1390535329575866369": "https://discord.com/api/webhooks/..."
}
```

## Classification Rules

### Amazon Detection
- Amazon.com/amzn.to links
- ASIN codes (B0XXXXXXXX pattern)

### Upcoming Detection
- Discord time tags (`<t:timestamp:R>`)
- Time keywords: "up next", "drop", "release", "tomorrow"
- Time patterns: "in X minutes/hours", "11:00 AM", "10/27"

### Mavely Detection
- Any HTTP/HTTPS links (non-Amazon)
- Attachments with URLs

### Default
- Messages that don't match above rules

## Bot Permissions

### Source Server (d2d.py)
- Read Message History
- View Channel

### Destination Server (message_forwarder.py, mention_bot.py)
- Read Message History
- View Channel
- Send Messages
- Embed Links
- Attach Files
- Mention Everyone (for mention bot)

## Dashboard Features

- **Real-time Monitoring**: Live view of message flow and bot status
- **Channel Management**: Add/edit channel mappings
- **Log Viewing**: Browse filtered messages by category
- **System Control**: Start/stop bots and view system status
- **Search & Filter**: Find specific messages across all logs

## Troubleshooting

### Common Issues

1. **Bots not starting**:
   - Check token validity in `config/tokenkeys.env`
   - Verify bot is invited to destination server
   - Check Python dependencies: `pip install -r requirements.txt`

2. **Messages not forwarding**:
   - Verify `config/channel_map.json` has correct webhook URLs
   - Check source channel IDs are correct
   - Ensure webhook URLs are valid and not expired

3. **Dashboard not loading**:
   - Ensure HTTP server is running on port 8080
   - Check firewall settings
   - Verify dashboard.html is accessible at /dashboard.html

4. **Classification not working**:
   - Check destination channel IDs in environment
   - Verify bot has permissions in destination channels
   - Review filterbot.py classification rules

### Log Files

- `logs/botlogs.json` - Bot startup, status, and system events
- `logs/d2dlogs.json` - Webhook forwarding activity
- `logs/filteredlogs.json` - Message classification and filtering

### Debug Mode

Set `VERBOSE=true` in `config/tokenkeys.env` for detailed console output.

## Security Notes

- **User Tokens**: Using Discord user tokens may violate Discord ToS
- **Webhook Security**: Keep webhook URLs private and rotate regularly
- **Bot Tokens**: Store securely and never commit to version control

## License

This project is for internal use only.