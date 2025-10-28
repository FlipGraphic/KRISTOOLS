# Channel Map UI Implementation

## Overview
Interactive Channel Map Manager UI integrated into the Discord2Discord dashboard for easy navigation and mapping control.

## Features Implemented

### ✅ Phase 1 - Core Functionality
- **Display Channel Mappings**: Shows all source → destination channel relationships from `config/channel_map.json`
- **Test Webhook Routes**: Click "Test Route" on any webhook to send a test message to Discord
- **Add New Mappings**: Modal form to add new source channel → webhook mappings
- **Edit Existing Mappings**: Edit webhook URLs for existing channel mappings
- **Delete Mappings**: Remove channel mappings with confirmation
- **Export Channel Map**: Download current channel map as JSON file
- **Import Channel Map**: Upload and replace channel map from JSON file
- **Pull Channels**: Placeholder endpoint for future Discord API integration

## Files Modified/Created

### Created Files
1. **`src/web/script.js`** - Channel Map frontend logic
   - `loadChannelMap()` - Fetches and renders channel mappings
   - `testWebhook(url)` - Sends test message to webhook
   - `pullChannelData()` - Placeholder for pulling channels from Discord API
   - `addChannelMapping()` - Adds new channel mapping
   - `editChannelMapping()` - Opens edit modal for existing mapping
   - `saveChannelMapping()` - Saves edited mapping
   - `deleteChannelMapping()` - Deletes mapping with confirmation
   - `exportChannelMap()` - Downloads channel map as JSON
   - `importChannelMap()` - Imports channel map from JSON file

### Modified Files
1. **`src/web/dashboard.html`**
   - Added Channel Map panel in right column (above Amazon panel)
   - Added CSS styles for channel entries and modals
   - Added 4 modals: Add, Edit, Import, and existing modals
   - Included `script.js` before closing body tag
   - Updated ESC key handler to close new modals

2. **`src/web/http_server.py`**
   - Added `/pull_channels` GET endpoint (Phase 1 placeholder)
   - Existing `/channel_map.json` endpoint serves the data
   - Existing `/save_channel_map` POST endpoint saves changes

## UI Layout

```
┌─────────────────────────────────────────────────────┐
│ 📋 Channels                            [🔄 Pull]    │
├─────────────────────────────────────────────────────┤
│ # Source: 1390535329575866368          [✏️ Edit]   │
│   Source Channel ID: 1390535329575866368            │
│   Webhook: 🔗 Test Route                            │
├─────────────────────────────────────────────────────┤
│ # Source: 1339718540177182872          [✏️ Edit]   │
│   Source Channel ID: 1339718540177182872            │
│   Webhook: 🔗 Test Route                            │
├─────────────────────────────────────────────────────┤
│                                                      │
│ [➕ Add]   [⬇️ Export]   [⬆️ Import]                │
└─────────────────────────────────────────────────────┘
```

## Usage Instructions

### Viewing Channel Mappings
1. Open dashboard: `http://localhost:8080/dashboard.html`
2. Scroll to the "📋 Channels" panel in the right column
3. All configured channel mappings are displayed

### Testing a Webhook
1. Click "🔗 Test Route" on any channel entry
2. A test message will be sent to the Discord webhook
3. Alert confirms success or failure

### Adding a New Mapping
1. Click "➕ Add" button at the bottom of the panel
2. Enter Source Channel ID (numeric Discord channel ID)
3. Enter Webhook URL (Discord webhook URL)
4. Click "Add" to save

### Editing a Mapping
1. Click "✏️ Edit" on any channel entry
2. Modify the Webhook URL (Source ID cannot be changed)
3. Click "Save" to update, or "Delete" to remove

### Exporting Channel Map
1. Click "⬇️ Export" button
2. JSON file downloads automatically as `channel_map_export.json`

### Importing Channel Map
1. Click "⬆️ Import" button
2. Select a JSON file with channel map data
3. Confirm replacement of current map
4. Click "Import" to apply

### Pulling Channels (Phase 2)
1. Click "🔄 Pull" button in panel header
2. Enter Source Server ID
3. Enter Destination Server ID
4. Phase 1: Returns placeholder count
5. Phase 2: Will integrate Discord API to fetch actual channels

## Technical Details

### Data Format
Channel map stored in `config/channel_map.json`:
```json
{
  "SOURCE_CHANNEL_ID": "https://discord.com/api/webhooks/WEBHOOK_ID/TOKEN",
  "1390535329575866368": "https://discord.com/api/webhooks/1430905295856472248/..."
}
```

### API Endpoints
- `GET /channel_map.json` - Serves current channel map
- `POST /save_channel_map` - Saves updated channel map
- `GET /pull_channels?src=SERVER_ID&dest=SERVER_ID` - Placeholder for channel pulling

### Validation
- Source Channel ID: Must be 8+ digit numeric string
- Webhook URL: Must start with `https://discord.com/api/webhooks/`

## Future Enhancements (Phase 2)

1. **Discord API Integration**
   - Fetch channels from source server using bot token
   - Fetch channels from destination server
   - Auto-create webhooks for destination channels
   - Match channels by name/category

2. **Advanced Features**
   - Bulk import/export with validation
   - Channel name resolution (show names instead of IDs)
   - Webhook health monitoring
   - Mapping templates

3. **UI Improvements**
   - Search/filter channel mappings
   - Sort by source/destination
   - Visual indicators for active/inactive webhooks
   - Drag-and-drop reordering

## Validation Checklist

- [x] Launch → `http://localhost:8080/dashboard.html`
- [x] Verify `/channel_map.json` populates the UI
- [x] Click Webhook → triggers "Test Route" message
- [x] Run **Pull** → see placeholder response
- [x] Test **Add** → confirm save to JSON
- [x] Test **Edit** → confirm update to JSON
- [x] Test **Delete** → confirm removal from JSON
- [x] Test **Export** → download JSON file
- [x] Test **Import** → upload and replace JSON

## Notes

- All changes follow Discord2Discord Bridge Suite Rules
- File headers added per project standards
- Modals close on ESC key press
- All operations include user confirmation for destructive actions
- Backend endpoints are tolerant of BOM in JSON files

