# 06. Data Model, Persistence, and Migrations

## Purpose
This document describes storage architecture and schema evolution mechanisms.

## Storage Topology

### Main application database
- Engine: SQLite (Peewee ORM)
- File path: `helper.db_path` (under `app/config/db/crafty.sqlite` by default)
- Initialization: `main.py` (`peewee.SqliteDatabase(..., pragmas={journal_mode: wal})`)

### Per-server stats databases
- Engine: SQLite per server
- Path pattern: `app/config/db/servers/{server_id}/crafty_server_stats.sqlite`
- Managed by `HelperServerStats` in `app/classes/models/server_stats.py`

Implication:
- Runtime and server metrics persistence are split across two DB layers.

## Main Models (selected)

### `Servers` (`app/classes/models/servers.py`)
Holds managed server configuration.

Important fields:
- identity/path/executable/command
- autostart and delay
- crash detection, stop command, ignored exits
- monitoring host/port/type
- shutdown timeout
- update watcher
- `cpu_affinity` (string; empty means unset)
- `memory_limit_mib` (integer MiB; `0` means disabled)
- `telemetry_port` (integer; `0` means disabled)
- `server_notes` (text; optional operator notes per server)

This table is the source of truth for server runtime settings.

### `Schedules` (`app/classes/models/management.py`)
Holds scheduler task definitions.

Used by `TasksManager` to create APScheduler jobs and queue commands.

### `Backups` (`app/classes/models/management.py`)
Holds backup policy/state per server.

### `CraftySettings` (`app/classes/models/management.py`)
Global settings row (secrets, login customizations, master server dir).

### Auth and permissions models
- users/api keys/roles/role-server mappings in `app/classes/models/users.py`, `roles.py`, `server_permissions.py`, `crafty_permissions.py`, etc.
- server permission bitmask now includes `NBT_READ` and `NBT_WRITE` bits (mask length increased from 8 to 10).

## Per-Server Stats Schema

`ServerStats` (`app/classes/models/server_stats.py`) stores sampled status snapshots:
- running/started
- cpu/memory stats
- `mem_capacity_raw` (bytes denominator used for `mem_percent`)
- player and ping data
- optional mod telemetry (`telemetry_tps`)
- update/import/crash flags

## Migration System

Migration framework: `app/classes/shared/migration.py`.

Conventions:
- migration scripts under `app/migrations` (main DB)
- stats migrations under `app/migrations/stats`
- startup calls `MigrationManager.up()` automatically

Pattern example:
- add column migration in `app/migrations/20250623_update_watcher.py`
- CPU affinity column migration in `app/migrations/20260417_cpu_affinity.py`
- memory limit column migration in `app/migrations/20260418_memory_limit_mib.py`
- server notes column migration in `app/migrations/20260420_server_notes.py`
- telemetry port column migration in `app/migrations/20260421_telemetry_port.py`
- NBT permission mask expansion migration in `app/migrations/20260421_nbt_permissions.py`
- per-server stats capacity column migration in `app/migrations/stats/20260418_mem_capacity_raw.py`
- per-server stats telemetry TPS migration in `app/migrations/stats/20260421_telemetry_tps.py`

Permission mask migration behavior:
- existing `role_servers.permissions` and `api_keys.server_permissions` values are expanded to 10 bits.
- legacy 8-bit masks preserve prior `FILES` intent by copying the old `FILES` bit into both new NBT bits (`NBT_READ` and `NBT_WRITE`).

Operational notes:
- Migrations run on startup; invalid migration code can block service startup.
- Rollback functions exist in scripts but runtime startup path uses forward migration.

## Data Access Patterns

- Helper classes (`HelperServers`, `HelpersManagement`, etc.) wrap model operations.
- Controllers often mutate model objects directly and then call save helper.
- Runtime instances re-fetch persisted settings when needed.

## Config and Persistence Coupling

Server config update path:
- API patch updates `Servers` row.
- Controller update triggers runtime object refresh.

This coupling is central when adding new server-level settings (such as future affinity fields).

## Risks and Fragility in Persistence Layer

- Some model field types and runtime expectations may diverge in edge paths.
- Broad exception handling around DB operations can hide root causes.
- Per-server DB creation and migration occur dynamically and can fail independently.

## Known Uncertainty

- Not all helper methods enforce explicit transaction boundaries for multi-step operations.
- Schedule model typing and schedule runtime checks do not appear perfectly aligned in all code paths.
