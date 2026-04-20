# 01. Architecture Overview

## Purpose
This document describes the runtime architecture and major boundaries in this repository.

See also:
- `Docs/00-runtime-flow-diagram.md` for the canonical one-page action and config flow.

## High-Level Layout

- Entry point: `main.py`
- Core runtime classes:
  - `app/classes/shared/main_controller.py` (`Controller`)
  - `app/classes/controllers/servers_controller.py` (`ServersController`)
  - `app/classes/shared/server.py` (`ServerInstance`)
  - `app/classes/shared/tasks.py` (`TasksManager`)
- Web server:
  - `app/classes/web/tornado_handler.py` (`Webserver`)
  - Route mapping in `app/classes/web/routes/api/api_handlers.py`
- Persistence:
  - Main SQLite DB via Peewee models in `app/classes/models/*.py`
  - Per-server stats SQLite DB via `app/classes/models/server_stats.py`
- Background/subsystems:
  - backups: `app/classes/shared/backup_mgr.py`
  - import/download: `app/classes/shared/import_helper.py`
  - monitoring/stats: `app/classes/remote_stats/stats.py`

## Architectural Shape

This codebase is a monolithic Python service with in-process controllers and schedulers.

### Main layers

1. Web/API layer (Tornado handlers)
- Accepts requests.
- Authenticates users/API keys.
- Validates request payloads (mostly JSON schema at handler level).
- Calls controller methods.

2. Controller layer
- Encapsulates app behavior across domains (users, roles, servers, management).
- Holds singleton-like state (notably loaded server instances).

3. Server runtime layer
- `ServerInstance` owns process lifecycle for one managed server.
- Uses Python threads and `subprocess.Popen` for process launch.
- Maintains per-server schedulers and runtime flags.

4. Persistence layer
- Peewee ORM for main app tables.
- Separate stats DB file per server (`crafty_server_stats.sqlite`).
- Migration framework in `app/classes/shared/migration.py` with versioned scripts under `app/migrations`.

## Runtime Concurrency Model

The system uses threads rather than async-first service boundaries.

- Main process starts web server, background schedulers, and queue watchers.
- `TasksManager` starts multiple daemon threads:
  - scheduler thread (`scheduler_thread`)
  - command queue consumer (`command_watcher`)
  - log watcher
  - realtime stats broadcaster
- Each `ServerInstance` starts additional threads:
  - process launch thread (`run_threaded_server` -> `start_server`)
  - console output reader (`ServerOutBuf.check`)
  - optional crash detection scheduler jobs
  - periodic stats and directory size jobs

Operational implication:
- Most state changes are in-memory and unsynchronized across many threads.
- Changes to process lifecycle code require careful reasoning about thread timing and race behavior.

## Request-to-Action Model

The most important operational pattern is command queue indirection:

- API request (for start/stop/restart/etc.) -> `ManagementController.send_command` -> in-memory `command_queue`
- `TasksManager.command_watcher` consumes queue and invokes server object methods.

This means external commands are serialized through one queue consumer path, which is useful for enforcing consistent launch behavior.

Canonical flow summary:
- `UI -> API -> ManagementController -> command_queue -> TasksManager.command_watcher -> ServerInstance -> subprocess.Popen`

## Process Management Model

Managed game servers are local OS processes launched by `ServerInstance.start_server` in `app/classes/shared/server.py`.

- Launch API: `subprocess.Popen([...], shell=False)`
- Multiple launch branches currently exist (bedrock/unix env, steam env, generic path).
- Lifecycle behavior (restart/crash recovery/scheduled starts) converges back to this launch path.

Important nuance:
- Crafty does not invoke a shell for launch (`shell=False`), but the first executable in `execution_command` may still be a script/wrapper chosen by operator config.
- Therefore, the tracked PID is not universally guaranteed to be a JVM PID unless launch commands are constrained accordingly.

## Configuration Model

Configuration exists at several levels:

- global app config: `app/config/config.json` (through `Helpers` getters/setters)
- server config: `Servers` table fields (e.g., `execution_command`, `auto_start`, `crash_detection`)
- scheduler config: `Schedules` table
- backup config: `Backups` table

UI/API changes usually persist to DB first, then runtime objects refresh from DB (`ServerInstance.reload_server_settings` and related controller refresh methods).

## Key Architectural Strengths

- Process launch and runtime behavior are concentrated in `ServerInstance`, making lifecycle features feasible.
- API route structure is explicit and centralized.
- Migration support exists and is used by startup.

## Key Architectural Weaknesses

- Heavy reliance on broad `except:` blocks in critical lifecycle paths.
- Thread-heavy runtime with limited explicit synchronization.
- Duplicated process launch branches in `start_server` increase maintenance risk.
- Some schema/runtime type mismatches and stale code paths (detailed in `08-fragility-and-technical-debt.md`).

## Known Uncertainty

- Legacy import path (`Import3`) references `controller.import_jar_server(...)`, but that method is not present in `Controller` at inspection time. This may be dead/unused or broken legacy behavior.
