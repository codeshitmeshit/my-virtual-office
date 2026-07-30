#!/usr/bin/env node
import fs from 'fs';
import path from 'path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const read = (rel) => fs.readFileSync(path.join(root, rel), 'utf8');
const exists = (rel) => fs.existsSync(path.join(root, rel));

const requiredFiles = [
  'app/server_routes/__init__.py',
  'app/server_routes/http.py',
  'app/server_routes/projects.py',
  'app/server_routes/providers.py',
  'app/server_routes/meetings.py',
  'app/server_routes/notifications.py',
  'app/server_routes/workflow.py',
  'app/server_routes/archive_room.py',
  'app/server_routes/agent_bridges.py',
  'app/server_routes/agents.py',
  'app/server_routes/skills.py',
  'app/server_routes/mcp_registry.py',
  'app/server_routes/config.py',
  'app/server_routes/browser.py',
  'app/server_services/__init__.py',
  'app/server_services/projects.py',
  'app/server_services/meetings.py',
  'app/server_services/providers.py',
  'app/server_services/notifications.py',
  'app/server_services/workflow.py',
  'app/server_services/archive_room.py',
  'app/server_services/agent_bridges.py',
  'app/server_services/agents.py',
  'app/server_services/skills.py',
  'app/server_services/mcp_registry.py',
  'app/server_services/config_runtime.py',
  'app/server_services/browser_runtime.py',
  'app/settings-common.js',
  'app/setup-settings.js',
  'app/main-menu-settings.js',
  'app/agent-creator-panel.js',
  'app/office-layout-editor.js',
  'app/weather-rendering.js',
  'app/office-rendering.js',
  'app/agent-model.js',
  'app/bubble-system.js',
  'app/office-ambient-animations.js',
  'app/office-loop.js',
  'app/sidebar-ui.js',
  'app/agent-modal-ui.js',
  'app/agent-workspace-panel.js',
  'app/agent-skills-management.js',
  'app/meetings-ui.js',
  'app/skills-library-ui.js',
  'app/mcp-registry-ui.js',
  'app/game-bootstrap.js',
];

for (const file of requiredFiles) {
  if (!exists(file)) throw new Error(`missing split file: ${file}`);
}

const server = read('app/server.py');
for (const marker of [
  'import server_routes',
  'from server_services import projects as _projects_service',
  'from server_services import meetings as _meetings_service',
  'from server_services import providers as _providers_service',
  'from server_services import notifications as _notifications_service',
  'from server_services import workflow as _workflow_service',
  'from server_services.workflow import *',
  'from server_services import archive_room as _archive_room_service',
  'from server_services.archive_room import *',
  'from server_services import agent_bridges as _agent_bridges_service',
  'from server_services.agent_bridges import *',
  'from server_services import agents as _agents_service',
  'from server_services.agents import *',
  'from server_services import skills as _skills_service',
  'from server_services.skills import *',
  'from server_services import config_runtime as _config_runtime_service',
  'from server_services.config_runtime import *',
  'from server_services import browser_runtime as _browser_runtime_service',
  'from server_services.browser_runtime import *',
  'server_routes.dispatch(self, "GET", parsed_url)',
  'server_routes.dispatch(self, "POST", parsed_url)',
  'server_routes.dispatch(self, "PUT", parsed_url)',
  'server_routes.dispatch(self, "DELETE", parsed_url)',
]) {
  if (!server.includes(marker)) throw new Error(`missing server dispatch marker: ${marker}`);
}

const routeInit = read('app/server_routes/__init__.py');
for (const marker of ['ROUTE_MODULES', 'def dispatch', 'config', 'browser', 'notifications', 'providers', 'skills', 'mcp_registry', 'agents', 'agent_bridges', 'meetings', 'archive_room', 'workflow', 'projects']) {
  if (!routeInit.includes(marker)) throw new Error(`missing route init marker: ${marker}`);
}

const routeHttp = read('app/server_routes/http.py');
for (const marker of ['def send_json', 'def read_json', 'def send_error_json', 'def require_origin']) {
  if (!routeHttp.includes(marker)) throw new Error(`missing http helper: ${marker}`);
}

for (const [file, markers] of Object.entries({
  'app/server_routes/projects.py': ['/api/projects', 'handle_get', 'handle_post', 'handle_put', 'handle_delete', 'from server_services import projects', 'projects_service._handle_project'],
  'app/server_routes/providers.py': ['/api/hermes/test', '/api/codex/test', '/api/claude-code/test', '/config/providers', 'from server_services import providers', 'providers_service._handle_codex_test'],
  'app/server_routes/meetings.py': ['/api/meetings', 'executable', 'requests', 'from server_services import meetings', 'meetings_service._handle_meeting'],
  'app/server_routes/notifications.py': ['/api/feishu-notification/config', '/api/feishu-notification/test', 'from server_services import notifications', 'notifications_service._feishu_notification_config_response'],
  'app/server_routes/workflow.py': ['/workflow/status', '/workflow/start', '/workflow/auto-mode', 'from server_services import workflow', 'workflow_service._handle_workflow_start'],
  'app/server_routes/archive_room.py': ['/api/archive-room', '/governance/', '/ai-refine', 'from server_services import archive_room', 'archive_service._handle_archive_room_overview'],
  'app/server_routes/agent_bridges.py': ['/api/codex/runs', '/api/hermes/chat', '/api/claude-code/runs', 'from server_services import agent_bridges', 'service._handle_codex_chat'],
  'app/server_routes/agents.py': ['/api/agents', '/api/agent-workspace/', '/api/agent-platform-communications/send', 'from server_services import agents', 'service._handle_agent_create'],
  'app/server_routes/skills.py': ['/api/skills-library', '/api/skills-workshop', '/api/agent/', 'from server_services import skills', 'service._handle_skills_library_list'],
  'app/server_routes/mcp_registry.py': ['/api/mcp-registry', 'from server_services import mcp_registry', 'service._handle_mcp_registry_list', 'service._handle_mcp_registry_register_openclaw'],
  'app/server_routes/config.py': ['/health', '/vo-config', '/setup/save', 'from server_services import config_runtime', 'service._handle_vo_config'],
  'app/server_routes/browser.py': ['/browser-status', '/browser-tabs', '/browser-viewer-status', 'from server_services import browser_runtime', 'service._handle_browser_status'],
})) {
  const content = read(file);
  for (const marker of markers) {
    if (!content.includes(marker)) throw new Error(`missing ${file} marker: ${marker}`);
  }
}

for (const [file, markers] of Object.entries({
  'app/server_services/projects.py': ['__all__', 'def _handle_project_create', 'def _handle_project_execution_start', 'def _handle_project_scheduled_cron_dispatch', 'def _wrap_exports'],
  'app/server_services/meetings.py': ['__all__', 'def _handle_meeting_request_create', 'def _handle_executable_meeting_run', 'def _meeting_history_projection', 'def _wrap_exports'],
  'app/server_services/providers.py': ['__all__', 'def _handle_hermes_test', 'def _handle_codex_test', 'def _handle_claude_code_test', 'def _wrap_exports'],
  'app/server_services/notifications.py': ['__all__', 'def _feishu_notification_config_response', 'def _save_feishu_notification_config', 'def _handle_feishu_card_action', 'def _wrap_exports'],
  'app/server_services/workflow.py': ['__all__', 'def _wf_run_pipeline', 'def _handle_workflow_start', 'def _wf_auto_resume_on_startup', 'def _wrap_exports'],
  'app/server_services/archive_room.py': ['__all__', 'def _handle_archive_room_overview', 'def _archive_maintenance_trigger', 'def _archive_manager_profile_check_on_startup', 'def _wrap_exports'],
  'app/server_services/agent_bridges.py': ['__all__', 'def _hydrate', 'def _handle_codex_chat', 'def _handle_hermes_chat', 'def _handle_claude_code_chat', 'def _wrap_exports'],
  'app/server_services/agents.py': ['__all__', 'def _get_agent_workspace_payload', 'def _handle_agent_platform_comm_send', 'def _handle_agent_create', 'def _handle_agent_delete', 'def _wrap_exports'],
  'app/server_services/skills.py': ['__all__', 'def _handle_skill_list', 'def _handle_skills_library_list', 'def _handle_skill_workshop_action', 'def _wrap_exports'],
  'app/server_services/mcp_registry.py': ['REGISTRY_FILENAME', 'def _handle_mcp_registry_list', 'def _handle_mcp_registry_save', 'def _handle_mcp_registry_register_openclaw'],
  'app/server_services/config_runtime.py': ['__all__', 'def _persist_setup_payload', 'def _build_safe_vo_config', 'def _handle_office_config_get', 'def _wrap_exports'],
  'app/server_services/browser_runtime.py': ['__all__', 'def _browser_viewer_probe', 'def _handle_browser_status', 'def _handle_browser_tabs', 'def _wrap_exports'],
})) {
  const content = read(file);
  for (const marker of markers) {
    if (!content.includes(marker)) throw new Error(`missing ${file} marker: ${marker}`);
  }
}

const agentBridgeService = read('app/server_services/agent_bridges.py');
for (const obsolete of [
  'class ProviderRunBridge',
  'PROVIDER_RUN_BRIDGE',
  'CLAUDE_CODE_STREAM_RUNS',
  '_CODEX_RUN_IDEMPOTENCY',
  '_PROVIDER_RUN_IDEMPOTENCY',
  '_register_provider_run_idempotency',
]) {
  if (agentBridgeService.includes(obsolete)) {
    throw new Error(`agent bridge service still contains obsolete run authority: ${obsolete}`);
  }
}

for (const marker of [
  'def _handle_codex_run_start',
  'def _handle_codex_run_events',
  'def _handle_hermes_run_start',
  'def _handle_hermes_run_events',
  'def _handle_claude_code_run_start',
  'def _handle_claude_code_run_events',
]) {
  if (!server.includes(marker)) throw new Error(`server.py missing authoritative provider run handler: ${marker}`);
  if (agentBridgeService.includes(marker)) {
    throw new Error(`agent bridge service still defines obsolete local run handler: ${marker}`);
  }
}

for (const [file, forbiddenMarkers] of Object.entries({
  'app/server_routes/projects.py': ['app._handle_project', 'app._handle_task', 'sys.modules[handler.__class__.__module__]'],
  'app/server_routes/meetings.py': ['app._handle_meeting', 'app._meeting_', 'sys.modules[handler.__class__.__module__]'],
  'app/server_routes/providers.py': ['app._handle_hermes_test', 'app._handle_codex_test', 'sys.modules[handler.__class__.__module__]'],
  'app/server_routes/notifications.py': ['app._feishu', 'app._save_feishu', 'sys.modules[handler.__class__.__module__]'],
  'app/server_routes/archive_room.py': ['app._archive', 'sys.modules[handler.__class__.__module__]'],
  'app/server_routes/agent_bridges.py': ['app._handle_codex', 'app._handle_hermes', 'sys.modules[handler.__class__.__module__]'],
  'app/server_routes/agents.py': ['app._handle_agent', 'sys.modules[handler.__class__.__module__]'],
  'app/server_routes/skills.py': ['app._handle_skill', 'sys.modules[handler.__class__.__module__]'],
  'app/server_routes/config.py': ['app._handle_', 'sys.modules[handler.__class__.__module__]'],
  'app/server_routes/browser.py': ['app._browser', 'sys.modules[handler.__class__.__module__]'],
})) {
  const content = read(file);
  for (const marker of forbiddenMarkers) {
    if (content.includes(marker)) throw new Error(`${file} still calls server shim: ${marker}`);
  }
}

const projectRoute = read('app/server_routes/projects.py');
for (const marker of ['_handle_workflow_start', '_handle_workflow_status', '/workflow/start', '/workflow/status', '/workflow/auto-mode']) {
  if (projectRoute.includes(marker)) throw new Error(`projects route still owns workflow branch: ${marker}`);
}

console.log('server/frontend module split checks passed');
