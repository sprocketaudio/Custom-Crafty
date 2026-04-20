# 11. PW0 Baseline and Smoke Matrix

## Purpose
This document is the PW0 baseline artifact required by:
- `Docs/10-affinity-prework-gate-plan.md` (PW0 exit criteria)

It captures:
- launch behavior snapshot from code before PW1 launch-path consolidation
- a repeatable manual smoke matrix for lifecycle paths that must remain stable

Inspection date:
- 2026-04-17

## Source-of-Truth Code Paths Inspected
- `app/classes/shared/server.py`
  - `run_threaded_server`
  - `setup_server_run_command`
  - `start_server`
  - `stop_server`
  - `restart_threaded_server`
  - `detect_crash`
  - `crash_detected`
  - `server_backup_threader`
  - `backup_server`
  - `threaded_jar_update`
- `app/classes/shared/tasks.py`
  - `command_watcher`
  - schedule enqueue paths (`_add_scheduler_command_job`, `schedule_watcher`)

## Baseline Launch Behavior (PW0 Snapshot)

## 1) Common pre-launch guards in `start_server`
These run before server-type launch branching:
- reject while global directory migration is active (`self.helper.dir_migration`)
- reject while import status is active (unless `forge_install=True`)
- reload settings and command (`setup_server_run_command`)
- reject if already running (`check_running`)
- reject if updating (`check_update`)
- Java EULA guard:
  - for `minecraft-java`, if `eula.txt` is not true and not forge installer path, launch is blocked

## 2) Launch command formation
- command source: `settings["execution_command"]`
- tokenization: `Helpers.cmdparse(...)`
- launch API: `subprocess.Popen(argv, shell=False, cwd=server_path, stdin=PIPE, stdout=PIPE, stderr=STDOUT)`

## 3) Per-type spawn branch behavior

1. `minecraft-bedrock` on Unix:
- branch condition: `not Helpers.is_os_windows()` and server type is `minecraft-bedrock`
- env adjustment: sets `LD_LIBRARY_PATH=server_path`
- launches with custom env

2. `steam_cmd`:
- optional `env.json` processing:
  - path-like keys are traversal-validated before merge
  - non-path keys are merged with append/prepend mode
- launches with possibly modified env

3. all other types (including `minecraft-java` and `hytale`):
- launches with default environment (no explicit env override)

## 4) Post-launch behavior (common)
- starts console reader thread (`ServerOutBuf.check`)
- resets crash flags and crash stats
- sets `start_time`
- if process is alive:
  - logs PID
  - records stats
  - sends websocket reload notifications
  - starts connectivity check thread
- if process exits immediately:
  - logs critical warning
- if crash detection enabled:
  - schedules `detect_crash` every 30s

## 5) Lifecycle trigger mapping baseline
- queue command dispatch (`TasksManager.command_watcher`):
  - `start_server` -> `run_threaded_server`
  - `stop_server` -> `stop_threaded_server`
  - `restart_server` -> `restart_threaded_server`
  - `backup_server` -> `server_backup_threader(action_id)`
  - `update_executable` -> `server_upgrade`
- schedule jobs enqueue the same command payload structure into the same queue path

## 6) Lifecycle-specific restart behavior baseline
- restart:
  - if not running -> start
  - if running -> stop, sleep 2s, start
- crash recovery:
  - `detect_crash` every 30s
  - restart attempted when crash detection enabled (up to restart counter threshold)
- update:
  - requires backup config
  - may stop running server, perform update, restart only if previously running
- backup:
  - optional before/after commands
  - optional shutdown before backup
  - restart only when `shutdown=true` and server was running before backup

## Known baseline caveats (must remain visible during PW1-PW4)
- at PW0 snapshot time, launch logic used multiple branch-specific spawn call sites
- process ownership depends on `execution_command` shape
- broad exception handling exists in several lifecycle-adjacent areas

## Repeatable Manual Smoke Matrix

Use this matrix before and after each pre-work phase.
Goal: detect behavioral regression while launch internals evolve.

### Test preconditions (all cases)
- create representative servers for each launch branch:
  - one default-branch server (`minecraft-java` or `hytale`)
  - one `minecraft-bedrock`
  - one `steam_cmd`
- ensure each server has valid executable/path and baseline working start command
- enable log capture and websocket/event observation
- keep one backup config available for update and backup tests

### Observables to collect for every case
- queue command observed (if queue-driven case)
- launch attempt log line
- resulting PID (if started)
- process running state from panel/runtime
- stop/restart outcome and user-visible notifications

## Matrix

1. `SMK-START-DEFAULT`
- Path: manual start
- Trigger: API/UI action -> `start_server`
- Target: one default-branch server (`minecraft-java` or `hytale`)
- Expected:
  - if target is `minecraft-java`, EULA gate enforced
  - process starts and PID is logged
  - console reader thread active

2. `SMK-START-BEDROCK`
- Path: manual start
- Trigger: API/UI action -> `start_server`
- Target: `minecraft-bedrock` on Linux
- Expected:
  - bedrock branch selected
  - process starts with `LD_LIBRARY_PATH` behavior intact

3. `SMK-START-STEAM`
- Path: manual start
- Trigger: API/UI action -> `start_server`
- Target: `steam_cmd`
- Expected:
  - steam branch selected
  - if `env.json` present, env merge behavior preserved
  - process starts and PID is logged

4. `SMK-RESTART`
- Path: manual restart
- Trigger: API/UI action -> `restart_server`
- Target: all three representative types
- Expected:
  - running server is stopped then started
  - non-running server starts directly
  - no stuck state in scheduler jobs

5. `SMK-CRASH-RECOVERY`
- Path: crash recovery restart
- Trigger: force process exit while crash detection enabled
- Target: at least one default-branch server (prefer `minecraft-java` for EULA coverage)
- Expected:
  - `detect_crash` identifies crash
  - restart path invoked via `crash_detected`
  - restart counter behavior preserved

6. `SMK-SCHEDULED-START`
- Path: scheduled start
- Trigger: scheduler enqueues `start_server`
- Target: at least one server type
- Expected:
  - command appears in queue
  - command watcher dispatches to `run_threaded_server`
  - server starts successfully

7. `SMK-SCHEDULED-RESTART`
- Path: scheduled restart
- Trigger: scheduler enqueues `restart_server`
- Target: at least one server type
- Expected:
  - restart path equivalent to manual restart
  - no queue dispatch mismatch

8. `SMK-UPDATE-RESTART`
- Path: update flow restart
- Trigger: `update_executable` command
- Target: at least one running server
- Expected:
  - backup phase runs first
  - server restarts only if it was running pre-update
  - update failure does not falsely report running state

9. `SMK-BACKUP-SHUTDOWN-RESTART`
- Path: backup-triggered restart
- Trigger: `backup_server` with backup config `shutdown=true`
- Target: at least one running server
- Expected:
  - server stops for backup
  - backup completes
  - server restarts only when `was_running` was true

10. `SMK-BACKUP-NO-RESTART`
- Path: backup without restart
- Trigger: `backup_server` with `shutdown=false`
- Target: at least one server
- Expected:
  - no forced restart behavior
  - backup notifications and status updates still emitted

## Latest Smoke Execution Snapshot (PW4 Validation Attempt)
Execution date:
- 2026-04-17

Environment:
- Windows 11 local workspace
- Python venv at `.venv`
- command used for runtime probe: `.venv\Scripts\python.exe main.py -d -i`

Observed runtime signals:
- migrations executed successfully
- web server started (`https:8443`)
- scheduler threads started
- no server start/restart events were generated

Data-state blockers (from local sqlite query):
- `servers`: `0`
- `schedules`: `0`
- `backups`: `0`

Matrix execution result in this environment:
1. `SMK-START-DEFAULT`: blocked (no configured default-branch server)
2. `SMK-START-BEDROCK`: blocked (no configured bedrock server; Linux-specific path)
3. `SMK-START-STEAM`: blocked (no configured steam server)
4. `SMK-RESTART`: blocked (no running/defined test server)
5. `SMK-CRASH-RECOVERY`: blocked (no crash-test target server)
6. `SMK-SCHEDULED-START`: blocked (no enabled schedule)
7. `SMK-SCHEDULED-RESTART`: blocked (no enabled schedule)
8. `SMK-UPDATE-RESTART`: blocked (no running server + update/backup fixture)
9. `SMK-BACKUP-SHUTDOWN-RESTART`: blocked (no backup config + running fixture)
10. `SMK-BACKUP-NO-RESTART`: blocked (no backup fixture)

Enablement required for full matrix run:
1. Create representative test servers for all launch branches (`minecraft-java` or `hytale`, plus `minecraft-bedrock`, plus `steam_cmd`).
2. Create at least one valid backup configuration.
3. Create schedule entries for start and restart paths.
4. Run on a Linux host for bedrock/Linux-specific assertions.
5. Keep Crafty running long enough to execute scheduled and crash-recovery cases.

## Operator-Reported Lifecycle Smoke (Current)
Execution date:
- 2026-04-17

Environment:
- local Windows workspace
- one configured `minecraft-java` server (default launch branch)
- panel-driven operations

Reported outcomes:
1. `SMK-START-DEFAULT` (`minecraft-java`): pass
2. stop from panel: pass
3. `SMK-RESTART` from panel: pass
4. `SMK-CRASH-RECOVERY`: pass (server force-closed, auto-restart triggered with crash detection + auto-start enabled)
5. `SMK-SCHEDULED-START`: pass
6. `SMK-SCHEDULED-RESTART`: pass

Still unvalidated in this phase:
- `SMK-START-BEDROCK` (Linux-only branch)
- `SMK-START-STEAM`
- update/backup restart paths (`SMK-UPDATE-RESTART`, `SMK-BACKUP-*`)
- direct `hytale` runtime smoke

Current execution decision for this fork:
- proceed with affinity implementation using shared launcher-path design
- accept deferred non-default-branch validation risk for now

## Pass/Fail Rule for PW0
PW0 is considered complete when:
1. this baseline document exists and is accurate to current code
2. the smoke matrix is reproducible
3. expected outcomes are explicit for representative server types

## PW0 Execution Status
- status: completed (documentation baseline)
- implementation changes: none
- next phase: PW1 (launch path consolidation)
