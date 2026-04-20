# 05. Web, API, and UI-to-Runtime Configuration Flow

## Purpose
This document explains routing, authentication, API structure, and how config changes propagate into runtime behavior.

## Web Server Composition

Web server implementation: `app/classes/web/tornado_handler.py` (`Webserver`).

Route registration includes:
- panel pages (`PanelHandler`)
- server pages (`ServerHandler`)
- websocket endpoint (`WebSocketHandler`)
- API v2 routes (expanded from `app/classes/web/routes/api/api_handlers.py`)
- metrics routes

## API Base Behavior

Base handler classes:
- `BaseHandler` (`app/classes/web/base_handler.py`)
- `BaseApiHandler` (`app/classes/web/base_api_handler.py`)

Authentication:
- Token sources: query param, `Authorization: Bearer`, or cookie.
- Token validation through `Controller.authentication` (`app/classes/shared/authentication.py`).
- Permission model combines user role permissions and API key restrictions.

Important security behavior:
- `BaseApiHandler.check_xsrf_cookie()` is overridden to `pass` (XSRF disabled for API routes).
- CORS defaults to `Access-Control-Allow-Origin: *` in `BaseHandler.set_default_headers()`.

## API Surface Structure

Route map is explicit in `app/classes/web/routes/api/api_handlers.py`.

Major domains:
- auth
- users
- roles
- servers
- backups/files/tasks/webhooks
- crafty settings/admin
- metrics

Server control and config endpoints of interest:
- `POST /api/v2/servers/{id}/action/{action}`
- `PATCH /api/v2/servers/{id}` (server config)
- `PATCH /api/v2/servers/{id}/update/config`
- schedule APIs under `/tasks`
- backup APIs under `/backups`

## UI Flow for Server Config Changes

Primary page: `app/frontend/templates/panel/server_config.html`.

Flow:
1. Browser form builds JSON payload client-side.
2. Superuser config UI performs syntax-level client validation for:
  - `cpu_affinity`
  - `memory_limit_mib` (non-negative integer MiB)
  - `telemetry_port` (integer `0..65535`; `0` disables custom telemetry probe)
  - `server_notes` (free-form text; no runtime enforcement)
3. Frontend sends `PATCH /api/v2/servers/{serverId}`.
4. Handler: `ApiServersServerIndexHandler.patch(...)` in `app/classes/web/routes/api/servers/server/index.py`.
5. JSON schema validation runs (`server_patch_schema` or `basic_server_patch_schema`).
6. For superuser patch payloads:
  - `cpu_affinity` is syntax-validated and canonicalized before persistence.
  - `memory_limit_mib` is canonicalized to non-negative integer MiB before persistence.
  - `telemetry_port` is validated as integer `0..65535` before persistence.
   - validator: `app/classes/helpers/cpu_affinity.py` (`canonicalize_cpu_affinity`)
   - effective Linux CPU-set applicability validation uses `os.sched_getaffinity(0)` when available
7. Handler applies fields to `server_obj` and persists via `self.controller.servers.update_server(server_obj)`.
8. `ServersController.update_server(...)` saves model and calls `server_instance.update_server_instance()`.
9. Runtime server instance reloads settings (`reload_server_settings`) from DB-backed values.

Outcome:
- Config updates are persisted and then reflected in in-memory server object.
- Running process behavior changes apply when relevant methods re-read settings or on next lifecycle event.
- For `cpu_affinity`, launch-time enforcement occurs in `ServerInstance.start_server`; unsupported host/runtime conditions produce deterministic startup failure (no silent fallback).
- For `memory_limit_mib`, launch-time enforcement configures Linux cgroup v2 memory cap and blocks startup if configured limit cannot be applied.
- For `telemetry_port`, runtime stats polling additionally queries `http://<server_ip>:<telemetry_port>/telemetry` for optional TPS/MSPT data when the server is running.

## UI Flow for Server Creation

Primary create pages:
- `app/frontend/templates/server/wizard.html` (Minecraft Java)
- `app/frontend/templates/server/bedrock_wizard.html`
- `app/frontend/templates/server/hytale_wizard.html`
- `app/frontend/templates/server/steam_wizard.html`

Flow:
1. Wizard form builds create payload client-side and sends `POST /api/v2/servers/`.
2. For superusers, wizard forms expose optional:
  - `cpu_affinity`
  - `memory_limit_mib`
  with client-side syntax validation.
3. `ApiServersIndexHandler.post(...)` validates create payload (`new_server_schema`).
4. If `cpu_affinity` is supplied:
  - non-superusers are rejected (`NOT_AUTHORIZED`),
  - superuser value is canonicalized with `canonicalize_cpu_affinity(...)`,
  - Linux effective CPU-set applicability is checked via `get_effective_cpu_set()`.
5. If `memory_limit_mib` is supplied:
  - non-superusers are rejected (`NOT_AUTHORIZED`),
  - superuser value is canonicalized via `canonicalize_memory_limit_mib(...)`.
6. `MainController.create_api_server(...)` forwards `cpu_affinity` and `memory_limit_mib` into `register_server(...)`.
7. `HelperServers.create_server(...)` persists both fields on the server model at creation time.

Operational effect:
- Newly created servers can have affinity configured immediately instead of requiring a post-create PATCH.
- Runtime enforcement remains launch-time in `ServerInstance.start_server`.

## UI Flow for `.dat` (NBT) File Editing

Primary pages/scripts:
- `app/frontend/templates/panel/server_file_edit.html`
- `app/frontend/static/assets/js/shared/editor.js`
- `app/frontend/static/assets/js/shared/files.js`

Backend path:
- `app/classes/web/routes/api/servers/server/files.py`
- `app/classes/helpers/nbt_helpers.py`

Flow:
1. Files list API marks `.dat` files as openable only when `nbtlib` is available and caller has `NBT_READ`.
2. Editor open still uses `GET page + POST /api/v2/servers/{id}/files`.
3. For `.dat`, backend requires `NBT_READ` and returns editor content based on requested mode:
  - `editor_encoding: "nbt_json"` (default) for easy JSON-style editing
  - `editor_encoding: "snbt"` for raw SNBT editing
4. Save uses existing `PATCH /api/v2/servers/{id}/files` path.
5. For `.dat`, backend requires `NBT_WRITE` and validates payload according to selected mode:
  - JSON mode parses JSON and coerces values to existing NBT tag types
  - SNBT mode parses SNBT directly
6. JSON mode does not allow introducing brand-new keys that are not already present in the file template.
7. Before NBT overwrite, backend writes an automatic backup copy: `<file>.crafty-nbt.bak`.
8. Invalid SNBT/JSON payloads are rejected with `NBT_PARSE_ERROR` and the live file is left unchanged.

Operational implication:
- `.dat` editing depends on Python package `nbtlib`.
- Without `nbtlib`, `.dat` files keep legacy behavior (not opened by default in the editor).
- Server permission masks now include `NBT_READ` and `NBT_WRITE` bits in addition to legacy file permission bits.

## Action Flow (Start/Stop/Restart/etc.)

Flow for most server actions:
1. API action endpoint (`ApiServersServerActionHandler.post`) validates authorization.
2. Calls `ManagementController.send_command(...)`.
3. Command payload enqueued.
4. `TasksManager.command_watcher()` executes mapped server method.

This indirection is central to runtime behavior.

## Handler Validation Patterns

Validation is mostly handler-level JSON schema checks.

Strength:
- explicit schema definitions are easy to locate.
- affinity input is canonicalized server-side before save (defense against malformed values reaching runtime layer).

Risk:
- inconsistent validation depth across endpoints.
- some transformations happen after validation (e.g., command composition), requiring careful review when adding new fields.

## Runtime Visibility and Websocket Updates

Websocket broadcasts are used heavily for:
- dashboard status updates
- terminal lines
- backup/update notifications
- server start/stop reload prompts

Per-server dashboard CPU semantics:
- Dashboard rows are driven by `ServerInstance.get_raw_server_stats(...)` (not historical DB snapshots) so the CPU display includes runtime `cpu_capacity_cores`.
- CPU usage value is affinity-aware because process CPU% is normalized by allowed CPU count in `app/classes/remote_stats/stats.py` (`_get_process_stats` + `_get_process_cpu_capacity`).
- If `telemetry_port` is configured and reachable, TPS is included in runtime websocket updates and server metrics datasets.
- Dashboard CPU label format is `X Cores - Y%` (desktop and mobile), where:
  - `X` = runtime CPU capacity for that process (`cpu_capacity_cores`),
  - `Y` = normalized process CPU usage percentage.
- Host-level CPU card remains host-wide usage and is intentionally not affinity-scoped per server.

Operational implication:
- behavior changes that affect lifecycle should also consider websocket event expectations.

## Known Uncertainty

- API and panel layers contain some duplicated or similar logic paths; full deduplication boundaries are not explicit.
- Not all endpoints appear to share consistent sanitization depth beyond schema validation and selective helper checks.
