# RS Agenda Tool

A Discord bot and web dashboard for managing RS (Reselling Secrets) agenda items, drops, and Amazon product tracking.

## Features

- **Discord Bot Integration**: Commands for creating channels, scheduling drops, and managing reminders
- **Amazon Product API**: Integration with Amazon PA-API for product information and pricing
- **Web Dashboard**: HTML interface for managing agenda items and viewing product data
- **Scheduler**: Automated message scheduling for drop announcements and reminders

## Project Structure

```
RS-Agenda-Tool/
├── src/                    # Python source files
│   ├── server.py          # Main Discord bot and HTTP server
│   └── amz_api_tool.py    # Amazon PA-API integration
├── config/                 # Configuration files
│   ├── apikeys.env        # API keys and tokens
│   └── agenda_data.json   # Persistent agenda data
├── web/                    # Web interface files
│   └── Daily.html         # Main dashboard
├── scripts/                # Launcher scripts
│   ├── run_all.bat        # Windows launcher
│   └── run_all.sh         # Linux/Mac launcher
├── docs/                   # Documentation
│   └── README.md          # This file
└── requirements.txt        # Python dependencies
```

## Quick Start

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   - Copy `config/apikeys.env.example` to `config/apikeys.env`
   - Fill in your Discord bot token and Amazon API credentials

3. **Run the Application**:
   - **Windows**: Double-click `scripts/run_all.bat`
   - **Linux/Mac**: Run `scripts/run_all.sh`

4. **Access Dashboard**:
   - Open http://127.0.0.1:8000/web/Daily.html in your browser

## Discord Bot Commands

- `!make <daily|instore|upcoming> <name>` - Create a new channel
- `!setdrop YYYY-MM-DD HH:MM [#channel]` - Schedule a drop
- `!setreminder <minutes> <@role|none> <message>` - Add reminder
- `!setlive <message>` - Set live announcement message
- `!schedule` - Start the scheduled sequence
- `!delete` - Delete current channel (mods only)
- `!transfer <category>` - Move channel to different category
- `!archive` - Archive channel to forum post

## Configuration

### Environment Variables (apikeys.env)

- `DISCORD_BOT_TOKEN` - Discord bot token
- `DISCORD_GUILD_ID` - Target Discord server ID
- `ARCHIVE_FORUM_ID` - Forum channel for archiving (optional)
- `CAT_DAILY`, `CAT_INSTORE`, `CAT_UPCOMING` - Category IDs for channel organization
- `ADMIN_ROLE_IDS` - Comma-separated role IDs with admin access
- `ADMIN_ROLE_NAMES` - Comma-separated role names with admin access

### Amazon API Configuration

- `PAAPI_PARTNER_TAG` - Amazon Associates partner tag
- `PAAPI_ACCESS_KEY` - Amazon PA-API access key
- `PAAPI_SECRET_KEY` - Amazon PA-API secret key
- `PAAPI_MARKETPLACE` - Target marketplace (default: www.amazon.com)

## API Endpoints

- `GET /health` - Server health check
- `GET /load_settings` - Load agenda settings
- `POST /save_settings` - Save agenda settings
- `POST /fetch_channels` - Fetch Discord channels
- `POST /discord/send_message` - Send Discord message
- `POST /scheduler/schedule_drop` - Schedule drop announcement
- `POST /scheduler/cancel` - Cancel scheduled drop
- `POST /paapi/get-items` - Get Amazon product info
- `POST /paapi/search-items` - Search Amazon products
- `POST /price` - Get price from Amazon link

## Troubleshooting

1. **Bot not responding**: Check Discord bot token and permissions
2. **Amazon API errors**: Verify PA-API credentials and marketplace settings
3. **Dashboard not loading**: Ensure HTTP server is running on port 8000
4. **Channels not created**: Verify category IDs and bot permissions

## License

This project is for internal use only.
