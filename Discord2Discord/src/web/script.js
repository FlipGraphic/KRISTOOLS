/* Helper Functions - Header Section: Channel Map Frontend Logic */

// ===== Channel Map Manager Functions =====

async function loadChannelMap() {
  try {
    const res = await fetch('/channel_map.json?' + Date.now());
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    renderChannelMapPanel(data);
  } catch (e) {
    console.error('[Channel Map] Failed to load:', e);
    document.getElementById('channel-map-list').innerHTML = '<div class="empty">Failed to load channel map</div>';
  }
}

function renderChannelMapPanel(channelMap) {
  const list = document.getElementById('channel-map-list');
  if (!channelMap || Object.keys(channelMap).length === 0) {
    list.innerHTML = '<div class="empty">No channel mappings configured</div>';
    return;
  }

  const entries = Object.entries(channelMap).map(([sourceId, webhookUrl]) => {
    // Extract webhook ID from URL for display
    const webhookMatch = webhookUrl.match(/webhooks\/(\d+)\//);
    const webhookId = webhookMatch ? webhookMatch[1] : 'N/A';
    
    return `
      <div class="channel-entry">
        <div class="channel-entry-header">
          <div class="channel-entry-title">
            <span class="channel-hash">#</span>
            <span class="channel-entry-name">Source: ${sourceId}</span>
          </div>
          <button class="edit-btn" onclick="editChannelMapping('${sourceId}', '${webhookUrl.replace(/'/g, "\\'")}')">✏️ Edit</button>
        </div>
        <div class="channel-entry-body">
          <div class="channel-entry-row">
            <span class="channel-entry-label">Source Channel ID:</span>
            <span class="channel-entry-value">${sourceId}</span>
          </div>
          <div class="channel-entry-row">
            <span class="channel-entry-label">Webhook:</span>
            <a href="${webhookUrl}" target="_blank" class="webhook-link" onclick="event.preventDefault(); testWebhook('${webhookUrl.replace(/'/g, "\\'")}')">
              🔗 Test Route
            </a>
          </div>
        </div>
      </div>
    `;
  }).join('');

  list.innerHTML = entries;
}

async function testWebhook(url) {
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content: '✅ Test Route successful! Channel Map UI is working.',
        username: 'Channel Map Tester'
      })
    });
    
    if (response.ok) {
      alert('✅ Webhook test successful!\n\nMessage sent to Discord.');
    } else {
      alert('⚠️ Webhook test failed!\n\nStatus: ' + response.status);
    }
  } catch (e) {
    alert('❌ Webhook test failed!\n\nError: ' + e.message);
  }
}

async function pullChannelData() {
  const srcServer = prompt('Enter Source Server ID:');
  const destServer = prompt('Enter Destination Server ID:');
  
  if (!srcServer || !destServer) {
    alert('⚠️ Missing input. Both Server IDs are required.');
    return;
  }

  try {
    const res = await fetch(`/pull_channels?src=${srcServer}&dest=${destServer}`);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    
    const data = await res.json();
    alert(`✅ Pulled ${data.count || 0} channels from ${srcServer} → ${destServer}`);
    
    // Reload the channel map
    await loadChannelMap();
  } catch (e) {
    alert('❌ Pull failed!\n\nError: ' + e.message + '\n\nCheck tokens or server access.');
  }
}

function showAddChannelModal() {
  document.getElementById('channel-map-add-modal').classList.add('show');
}

function hideAddChannelModal() {
  document.getElementById('channel-map-add-modal').classList.remove('show');
  document.getElementById('add-source-id').value = '';
  document.getElementById('add-webhook-url').value = '';
}

async function addChannelMapping() {
  const sourceId = document.getElementById('add-source-id').value.trim();
  const webhookUrl = document.getElementById('add-webhook-url').value.trim();
  
  // Validation
  if (!/^\d{8,}$/.test(sourceId)) {
    alert('⚠️ Invalid Source Channel ID\n\nMust be a numeric Discord channel ID.');
    return;
  }
  
  if (!/^https?:\/\/discord\.com\/api\/webhooks\//i.test(webhookUrl)) {
    alert('⚠️ Invalid Webhook URL\n\nMust be a Discord webhook URL.');
    return;
  }

  try {
    // Load current map
    const res = await fetch('/channel_map.json?' + Date.now());
    const currentMap = res.ok ? await res.json() : {};
    
    // Add new mapping
    currentMap[sourceId] = webhookUrl;
    
    // Save to server
    const saveRes = await fetch('/save_channel_map', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentMap)
    });
    
    if (saveRes.ok) {
      alert('✅ Channel mapping added successfully!');
      hideAddChannelModal();
      await loadChannelMap();
    } else {
      alert('❌ Failed to save channel map\n\nStatus: ' + saveRes.status);
    }
  } catch (e) {
    alert('❌ Error saving channel map\n\nError: ' + e.message);
  }
}

function editChannelMapping(sourceId, webhookUrl) {
  document.getElementById('edit-source-id').value = sourceId;
  document.getElementById('edit-source-id').disabled = true; // Can't change source ID
  document.getElementById('edit-webhook-url').value = webhookUrl;
  document.getElementById('edit-original-source-id').value = sourceId;
  document.getElementById('channel-map-edit-modal').classList.add('show');
}

function hideEditChannelModal() {
  document.getElementById('channel-map-edit-modal').classList.remove('show');
  document.getElementById('edit-source-id').value = '';
  document.getElementById('edit-webhook-url').value = '';
  document.getElementById('edit-original-source-id').value = '';
}

async function saveChannelMapping() {
  const originalSourceId = document.getElementById('edit-original-source-id').value;
  const sourceId = document.getElementById('edit-source-id').value.trim();
  const webhookUrl = document.getElementById('edit-webhook-url').value.trim();
  
  // Validation
  if (!/^https?:\/\/discord\.com\/api\/webhooks\//i.test(webhookUrl)) {
    alert('⚠️ Invalid Webhook URL\n\nMust be a Discord webhook URL.');
    return;
  }

  try {
    // Load current map
    const res = await fetch('/channel_map.json?' + Date.now());
    const currentMap = res.ok ? await res.json() : {};
    
    // Update mapping
    currentMap[sourceId] = webhookUrl;
    
    // Save to server
    const saveRes = await fetch('/save_channel_map', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentMap)
    });
    
    if (saveRes.ok) {
      alert('✅ Channel mapping updated successfully!');
      hideEditChannelModal();
      await loadChannelMap();
    } else {
      alert('❌ Failed to save channel map\n\nStatus: ' + saveRes.status);
    }
  } catch (e) {
    alert('❌ Error saving channel map\n\nError: ' + e.message);
  }
}

async function deleteChannelMapping() {
  if (!confirm('⚠️ Delete this channel mapping?\n\nThis action cannot be undone.')) {
    return;
  }

  const sourceId = document.getElementById('edit-source-id').value.trim();

  try {
    // Load current map
    const res = await fetch('/channel_map.json?' + Date.now());
    const currentMap = res.ok ? await res.json() : {};
    
    // Delete mapping
    delete currentMap[sourceId];
    
    // Save to server
    const saveRes = await fetch('/save_channel_map', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentMap)
    });
    
    if (saveRes.ok) {
      alert('✅ Channel mapping deleted successfully!');
      hideEditChannelModal();
      await loadChannelMap();
    } else {
      alert('❌ Failed to save channel map\n\nStatus: ' + saveRes.status);
    }
  } catch (e) {
    alert('❌ Error saving channel map\n\nError: ' + e.message);
  }
}

async function exportChannelMap() {
  try {
    const res = await fetch('/channel_map.json?' + Date.now());
    if (!res.ok) throw new Error('HTTP ' + res.status);
    
    const data = await res.json();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'channel_map_export.json';
    document.body.appendChild(a);
    a.click();
    a.remove();
    
    alert('✅ Channel map exported successfully!');
  } catch (e) {
    alert('❌ Export failed!\n\nError: ' + e.message);
  }
}

function showImportChannelModal() {
  document.getElementById('channel-map-import-modal').classList.add('show');
}

function hideImportChannelModal() {
  document.getElementById('channel-map-import-modal').classList.remove('show');
  document.getElementById('import-file-input').value = '';
}

async function importChannelMap() {
  const fileInput = document.getElementById('import-file-input');
  const file = fileInput.files[0];
  
  if (!file) {
    alert('⚠️ No file selected');
    return;
  }

  try {
    const text = await file.text();
    const importedMap = JSON.parse(text);
    
    // Validate structure
    if (typeof importedMap !== 'object' || Array.isArray(importedMap)) {
      throw new Error('Invalid channel map format');
    }

    // Confirm import
    const count = Object.keys(importedMap).length;
    if (!confirm(`⚠️ Import ${count} channel mapping(s)?\n\nThis will replace the current channel map.`)) {
      return;
    }

    // Save to server
    const saveRes = await fetch('/save_channel_map', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(importedMap)
    });
    
    if (saveRes.ok) {
      alert('✅ Channel map imported successfully!');
      hideImportChannelModal();
      await loadChannelMap();
    } else {
      alert('❌ Failed to save imported channel map\n\nStatus: ' + saveRes.status);
    }
  } catch (e) {
    alert('❌ Import failed!\n\nError: ' + e.message);
  }
}

// Initialize Channel Map on page load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('channel-map-container')) {
      loadChannelMap();
    }
  });
} else {
  // DOM already loaded
  if (document.getElementById('channel-map-container')) {
    loadChannelMap();
  }
}

