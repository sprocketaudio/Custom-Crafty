# 09. Safe Modification Playbook

## Purpose
This document is a checklist for making changes safely in lifecycle-critical parts of this project.
Use it before opening implementation PRs that touch launch/runtime behavior.

## 1) If You Modify Process Launch (`ServerInstance.start_server`)

Files:
- `app/classes/shared/server.py`
- `app/classes/helpers/helpers.py` (`cmdparse`)

Minimum verification checklist:
- start path works
- restart path works (`restart_threaded_server`)
- crash recovery restart works (`detect_crash` / `crash_detected`)
- scheduled start/restart works (`TasksManager.command_watcher` via queued commands)
- update restart path works (`threaded_jar_update`)
- backup-triggered restart works (`backup_server` when `shutdown` is enabled)
- launch capability guards are validated at startup and at launch-time checks (for example dependency/tool availability)
- PID tracked by Crafty matches intended process ownership model
- stop/kill still terminate expected process tree
- stats polling still reports expected process

Do not:
- add shell-based launch string concatenation
- bypass centralized launch enforcement in `_resolve_launch_command` / `_launch_server_process`

## 2) If You Modify Queueing or Task Dispatch

Files:
- `app/classes/controllers/management_controller.py`
- `app/classes/shared/tasks.py`

Minimum verification checklist:
- command payload schema assumptions remain consistent (`server_id`, `user_id`, `command`, optional `action_id`)
- command ordering and single-consumer behavior still hold
- unknown or invalid server IDs are handled deterministically
- schedule-generated commands still execute through the same queue path
- audit log behavior remains correct for user-issued actions

Risk to watch:
- queue is in-memory only; changes can silently drop or duplicate operational commands.

## 3) If You Modify Models / Persistence

Files:
- `app/classes/models/*.py`
- `app/migrations/*.py`
- `app/classes/shared/migration.py`

Minimum verification checklist:
- add migration for every schema change
- define default values and backward behavior
- confirm startup migration path succeeds on existing DBs
- confirm API serialization/deserialization includes new fields where expected
- confirm runtime object refresh paths load new values (`ServersController.update_server`, `ServerInstance.reload_server_settings`)

Do not:
- merge model-field changes without migration impact review
- assume only fresh installs matter

## 4) If You Modify API/UI Config Surfaces

Files:
- API handlers under `app/classes/web/routes/api/...`
- templates under `app/frontend/templates/panel/...`
- panel page data assembly in `app/classes/web/panel_handler.py`

Minimum verification checklist:
- JSON schema updated
- permission gate updated (superuser vs non-superuser semantics)
- UI payload includes new fields
- failed-server and fallback render paths tolerate new fields
- runtime behavior reflects saved values
- validation errors are deterministic and operator-readable

## 5) If You Modify Scheduling

Files:
- `app/classes/shared/tasks.py`
- schedule model helpers in `app/classes/models/management.py`

Minimum verification checklist:
- one-time and recurring schedules still run as expected
- reaction/child task behavior still triggers correctly
- schedule reload from DB behaves correctly after restart
- duplicate job IDs and stale jobs are handled safely

## 6) Security and Operational Gate (Always)

Before merging:
- review command-construction paths for injection regressions
- confirm privilege boundaries are unchanged or intentionally tightened
- verify traversal-sensitive paths still call `validate_traversal` where required
- confirm failure semantics are explicit (not silent fallback in safety-critical behavior)
- add logs for operator-visible failures affecting start/stop/update/restore

## 7) Performance Gate (Always)

Before merging:
- evaluate polling frequency and blocking calls on hot paths
- evaluate additional CPU/memory overhead for per-server loops
- avoid adding high-latency work into queue consumer loops without reason
- document expected performance tradeoffs

## 8) Documentation Gate (Always)

Before merging:
- update existing `/Docs` files affected by behavior changes
- add a new doc only if current docs cannot represent the change clearly
- record unresolved risks and assumptions explicitly
