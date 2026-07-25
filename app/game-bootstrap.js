// Final startup after split modules have registered their globals.
initOfficeConfig();

// Load server config (async — merges on arrival).
_loadServerConfig();

// Migrate: ensure interior walls array exists.
if (!officeConfig.walls.interior) officeConfig.walls.interior = [];
buildCollisionGrid();

// Kick off roster fetch after agent/editor modules are available.
_fetchRoster();

// Start chat polling after the bubble module has registered pollAgentChat.
setInterval(pollAgentChat, 3000);
pollAgentChat();

loop();
