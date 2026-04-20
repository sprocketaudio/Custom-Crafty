# 14. CurseForge Modpack Update Center Specification

## Purpose
Define a production-safe implementation for modpack update automation in Crafty Update Center using the CurseForge API, with explicit backup, purge, overlay restore, and loader-alignment behavior.

This document is a feature specification only. It does not indicate completed implementation.

## Scope
In-scope:
- Per-server CurseForge update profile configuration.
- Check-latest flow for a selected CurseForge project.
- Apply-update flow for server packs with:
  - mandatory backup gate,
  - configurable purge paths,
  - extraction/install of server files,
  - overlay re-apply,
  - optional Forge/NeoForge installer alignment.
- UI integration into existing `update_center`.
- API and migration design.
- Failure handling and rollback expectations.

Out-of-scope (initial version):
- Automated launcher-driven server pack generation when CurseForge does not provide a server pack.
- Multi-provider abstraction (Modrinth/FTB) in v1.
- Fully automatic scheduled modpack updates in v1 (manual trigger only).

## User Requirements (Captured)
- Feature is private-ops focused (single operator, multiple public servers).
- Some packs do not provide full server zips; in that case workflow must stop and operator updates manually.
- Purge targets must be configurable per server (example: `mods`, `config`, `defaultconfigs`, `kubejs`).
- Overlay restore must be supported from an operator-managed folder structure.
- Backup must occur before mutation.
- Forge/NeoForge version should align with the updated modpack when applicable.
- API key/rate-limit behavior must be explicit.

## Existing Baseline (Current Code)

### Update Center UI and Routes
- Page template: `app/frontend/templates/panel/server_update_center.html`
- Subpage route wiring: `app/classes/web/panel_handler.py` (`subpage == "update_center"`)
- Existing API endpoint used by UI:
  - `PATCH /api/v2/servers/{id}/update/config/`
  - handler: `ApiServersServerUpdateConfig` in `app/classes/web/routes/api/servers/server/index.py`
- Existing update action button dispatches:
  - `POST /api/v2/servers/{id}/action/update_executable`
  - queue consumer mapping in `app/classes/shared/tasks.py` to `ServerInstance.server_upgrade()`

### Existing Update Mechanisms
- BigBucket jar metadata/cache and jar download:
  - `app/classes/big_bucket/bigbucket.py`
- Existing executable update path:
  - `ServerInstance.server_upgrade()` in `app/classes/shared/server.py`
- Forge/NeoForge installer post-run reconfiguration:
  - `ServerInstance.forge_install_watcher()` in `app/classes/shared/server.py`

### Existing File/Import Utilities
- Archive extraction with traversal checks:
  - `FileHelpers.unzip_file()` in `app/classes/helpers/file_helpers.py`
- Import/download helpers:
  - `app/classes/shared/import_helper.py`

## Functional Requirements

### FR-1: Per-server modpack profile
Each server can store a CurseForge profile used by Update Center.

Minimum profile fields:
- provider (fixed to `curseforge` in v1)
- project identifier (CurseForge project ID)
- selected release channel (`release`, `beta`, `alpha`)
- optional pinned file ID (if pin mode is enabled)
- purge path list (relative paths under server root)
- overlay root path (absolute path on host)
- behavior flags:
  - require_server_pack (default `true`)
  - auto_backup_before_apply (default `true`)
  - restart_after_apply_if_previously_running (default `true`)
  - align_mod_loader (default `true`)

### FR-2: Check latest
Operator can request latest eligible file metadata for the configured project/channel.

Outputs:
- latest file ID
- display name/version
- release type
- publish time
- whether a server pack artifact is available
- compatibility summary (when derivable)

### FR-3: Apply update (manual trigger)
Operator can run a controlled update pipeline from Update Center.

Pipeline must:
1. Acquire per-server update lock.
2. Mark update status for UI.
3. Backup server (required unless explicitly disabled).
4. Stop server if running (track `was_running`).
5. Resolve target CurseForge file and server pack artifact.
6. Abort cleanly if no server pack (when `require_server_pack=true`).
7. Download to staging area under `temp`.
8. Extract staged archive safely.
9. Purge configured paths in live server root.
10. Copy extracted server pack content into server root.
11. Re-apply overlay content.
12. Align Forge/NeoForge if enabled and required.
13. Restart if `was_running` and restart policy allows.
14. Clear update status and emit completion notifications.

### FR-4: No-server-pack fallback
If no server package exists:
- no destructive mutation is performed,
- run status is set to failed with specific reason (`NO_SERVER_PACK`),
- UI tells operator to perform manual update.

### FR-5: Purge safety
Configured purge paths must be validated:
- relative path only,
- cannot traverse (`..`),
- must resolve under server root,
- deny protected roots (`.`, empty path, root separators, Crafty DB/config paths).

Default purge list (new profile default):
- `mods`
- `config`
- `defaultconfigs`
- `kubejs`

### FR-6: Overlay merge
Overlay root supports operator-owned patch content.

Expected layout (recommended):
- `<overlay_root>/mods/`
- `<overlay_root>/config/`
- `<overlay_root>/defaultconfigs/`
- `<overlay_root>/kubejs/`
- optional `<overlay_root>/overlay.json` for future behavior flags

Merge semantics:
- recursive copy from overlay subtree to server subtree,
- overwrite existing files,
- create missing directories,
- leave unspecified files untouched.

### FR-7: Loader alignment
When pack metadata indicates Forge or NeoForge:
- derive desired loader family/version,
- if mismatch with current server, run installer alignment.

Alignment strategy:
- leverage existing Forge/NeoForge installer workflow used by BigBucket (`forge_install=True` path and `forge_install_watcher()`).
- if required installer artifact/version is unavailable, fail with explicit reason and do not partially mutate loader state.

### FR-8: Permission model
Use existing server permissions:
- Require `CONFIG` for profile edits/check/apply from Update Center.
- Require `COMMANDS` to execute the queued update action.

### FR-9: Audit and notifications
Each run must create audit entries with:
- actor,
- server ID,
- action (`check`, `apply`, `rollback`),
- result and reason code.

Websocket notifications should mirror existing update patterns (`notification`, `send_start_reload`, progress updates).

### FR-10: Idempotent failure handling
On failure before destructive phase: no server mutations.
On failure after destructive phase: leave backup available and clearly mark manual restore path.

## Proposed Architecture

### New components
- `app/classes/helpers/curseforge_client.py`
  - typed API wrapper for CurseForge REST calls.
  - header auth with API key.
  - bounded retries and 429 backoff.
- `app/classes/shared/modpack_updater.py`
  - orchestrates update pipeline.
  - owns run-state transitions, locking, and failure semantics.

### Existing components reused
- `BackupManager` and existing backup config resolution.
- `FileHelpers` for secure extraction and file operations.
- `ImportHelpers` patterns for threaded long-running work.
- `ManagementController` command queue for asynchronous execution.
- `ServerInstance` stop/start lifecycle methods.

### Command queue integration
Add action dispatch:
- API action: `update_modpack`
- queue consumer (`TasksManager.command_watcher`) branch:
  - `case "update_modpack": svr.run_threaded_modpack_update(user_id)`

## Global Configuration Additions

Recommended additions to `MASTER_CONFIG` / `config.json`:
- `curseforge_api_base`: default `https://api.curseforge.com`
- `curseforge_api_timeout_seconds`: default `10`
- `curseforge_api_retries`: default `3`
- `curseforge_api_backoff_base_seconds`: default `2`
- `curseforge_cache_ttl_seconds`: default `600`
- `curseforge_api_key_env_var`: default `CURSEFORGE_API_KEY`

Key resolution order:
1. environment variable named by `curseforge_api_key_env_var`
2. optional local config key `curseforge_api_key` (not recommended)

Rules:
- Never return API key values in API responses.
- Never write API key values into audit logs.

## Persistence and Migrations

### New table: `server_modpack_profiles`
Recommended fields:
- `server_id` FK (unique per server)
- `provider` (`curseforge`)
- `project_id` (int)
- `release_channel` (`release|beta|alpha`)
- `pinned_file_id` (nullable int)
- `purge_paths_json` (text json array)
- `overlay_root` (text)
- `require_server_pack` (bool)
- `auto_backup_before_apply` (bool)
- `restart_if_was_running` (bool)
- `align_mod_loader` (bool)
- `last_checked_file_id` (nullable int)
- `last_applied_file_id` (nullable int)
- `updated` timestamp

### New table: `server_modpack_runs` (recommended)
For operator diagnostics:
- run ID, server ID, actor, started/finished
- target file ID
- status (`pending|running|success|failed`)
- reason code
- summary json (backup ID, paths touched, loader action)

### Migration files
Expected new migrations:
- `app/migrations/<timestamp>_modpack_profiles.py`
- `app/migrations/<timestamp>_modpack_runs.py`

## API Specification (v2)

### Profile CRUD
- `GET /api/v2/servers/{id}/modpack/profile`
- `PATCH /api/v2/servers/{id}/modpack/profile`

### Latest check
- `POST /api/v2/servers/{id}/modpack/check`
Request:
- optional `force_refresh` bool

Response:
- latest file metadata
- availability flags
- comparison against last applied

### Apply update
- `POST /api/v2/servers/{id}/modpack/apply`
Request:
- optional `target_file_id`
- optional `dry_run` (v1 may support check-only response)

Behavior:
- queues `update_modpack` command with resolved profile/action payload.

### Run status
- `GET /api/v2/servers/{id}/modpack/runs?limit=...`
- `GET /api/v2/servers/{id}/modpack/runs/{run_id}`

## UI Specification

### Update Center additions (`server_update_center.html`)
- New "Modpack Update" card:
  - enable toggle (profile active)
  - project ID input
  - channel select
  - purge paths editor (tag/list UI)
  - overlay path input
  - check latest button
  - apply update button
  - last run summary

### Guardrails in UI
- warn before apply when purge list is non-empty.
- show explicit manual fallback message for no-server-pack.
- show backup ID used for the run.

## Security and Safety Requirements
- API key must never be returned to client.
- Prefer environment variable source (`CURSEFORGE_API_KEY`) with optional config fallback.
- If fallback config key is allowed, redact in logs and support endpoint responses.
- Validate all filesystem paths against server root and expected overlay root.
- Reject symlink traversal and zip-slip paths before extraction/copy.
- Enforce one modpack update run at a time per server.

## Rate Limiting and Caching
- Cache latest-check responses per `project_id + channel` with short TTL (example: 5-15 minutes).
- Exponential backoff for 429/5xx responses.
- Circuit-breaker behavior after repeated failures to avoid hammering API.

## Failure Semantics and Reason Codes
Use structured reason codes for UI and logs:
- `NO_PROFILE_CONFIGURED`
- `CF_API_AUTH_FAILED`
- `CF_RATE_LIMITED`
- `NO_SERVER_PACK`
- `BACKUP_FAILED`
- `PURGE_VALIDATION_FAILED`
- `OVERLAY_PATH_INVALID`
- `LOADER_ALIGNMENT_UNAVAILABLE`
- `LOADER_ALIGNMENT_FAILED`
- `EXTRACTION_FAILED`
- `COPY_FAILED`

## Testing Strategy

### Unit tests
- CurseForge client response mapping and retry behavior.
- purge path normalization/validation.
- overlay merge behavior.
- loader manifest parsing and alignment decision logic.

### Integration tests
- full apply pipeline with mocked API and temp filesystem.
- failure injection at each pipeline stage to verify rollback behavior.

### Manual smoke matrix
- running vs stopped server start state.
- no-server-pack project.
- overlay enabled/disabled.
- purge list empty vs populated.
- Forge/NeoForge alignment required vs not required.

## Rollout Plan
- Phase 1: data model + profile API + UI form (no apply).
- Phase 2: latest-check API + UI status.
- Phase 3: apply pipeline without loader alignment.
- Phase 4: Forge/NeoForge alignment integration.
- Phase 5: polish (run history, richer telemetry, optional scheduled checks).

## Operational Notes
- v1 should default to manual invocation from Update Center.
- Any destructive action must be backup-gated.
- If run fails after purge/extract stages, operator should restore from backup via existing backup UI.

## Open Decisions
- Exact mapping source from CurseForge file metadata to Forge/NeoForge installer version.
- Whether to implement `server_modpack_runs` in v1 or add in v2.
- Whether to allow non-superusers with `CONFIG` + `COMMANDS` to apply updates by default.
- Whether to expose dry-run output in v1 UI.
