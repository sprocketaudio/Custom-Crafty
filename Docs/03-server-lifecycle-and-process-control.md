# 03. Server Lifecycle and Process Control

## Purpose
This document explains exactly how a managed server process is created, started, supervised, restarted, updated, backed up, restored, and stopped.

Primary runtime class: `app/classes/shared/server.py` (`ServerInstance`).

Baseline test companion:
- `Docs/11-pw0-baseline-and-smoke-matrix.md` (repeatable smoke checks used during pre-work phases)

## Lifecycle Entry Points

### Object creation and setup
- `ServersController.init_all_servers()` creates `ServerInstance` objects.
- `ServerInstance.do_server_setup(server_data_obj)`:
  - stores settings
  - records initial stats
  - schedules autostart if enabled (`run_scheduled_server`)

### Manual or scheduled action dispatch
Commands are usually routed through queueing:
- API action handler (`app/classes/web/routes/api/servers/server/action.py`) calls `ManagementController.send_command()`.
- `ManagementController.queue_command()` pushes into in-memory queue.
- `TasksManager.command_watcher()` matches command strings and calls server methods.

Important command mappings in `TasksManager.command_watcher()`:
- `start_server` -> `svr.run_threaded_server(user_id)`
- `stop_server` -> `svr.stop_threaded_server()`
- `restart_server` -> `svr.restart_threaded_server(user_id)`
- `update_executable` -> `svr.server_upgrade()`
- `backup_server` -> `svr.server_backup_threader(action_id)`

## Start Path

### Threaded launch wrapper
- `ServerInstance.run_threaded_server(user_id, forge_install=False)`:
  - spawns a daemon thread targeting `start_server`
  - schedules runtime stats polling jobs (`realtime_stats`, `record_server_stats`)

### Start implementation
- `ServerInstance.start_server(...)` does:
  1. reloads settings (`setup_server_run_command`)
  2. refuses start if already running or updating
  3. prepares memory-limit policy (`_prepare_memory_limit_policy(...)`) when `memory_limit_mib > 0`
  4. resolves effective launch argv (`_resolve_launch_command(...)`), including CPU affinity `taskset` prefix when configured
  5. validates EULA for Java servers unless forge installer path
  6. chooses server-type branch settings (env/guards) and launches via `_launch_server_process(...)`
  7. attaches spawned PID to cgroup when memory limit is active (`_attach_process_to_memory_cgroup(...)`)
  8. runs wrapper-policy ownership hook (`_apply_wrapper_policy(...)`)
     - in affinity-enabled or memory-limit-enabled launches, fork-and-exit wrapper shapes are enforced as startup failure even if wrapper policy mode is otherwise disabled
  9. starts console output reader (`ServerOutBuf.check`)
  10. records runtime status
  11. starts crash detection watcher if enabled

### Launch behavior
Current launch mechanism:
- centralized spawn helper: `ServerInstance._launch_server_process(...)`
- helper calls `subprocess.Popen(list_args, shell=False)`
- cwd is server directory
- stdin/stdout are piped for console interaction
- server type branches adjust env vars and startup handling
- launch command resolution is centralized via `ServerInstance._resolve_launch_command(...)`:
  - empty `cpu_affinity`: original command
  - configured `cpu_affinity`: validates/canonicalizes and prefixes `taskset --cpu-list ...`
  - host without affinity capability: startup blocked deterministically
- memory-limit resolution is centralized via `ServerInstance._prepare_memory_limit_policy(...)`:
  - empty/zero `memory_limit_mib`: disabled
  - configured positive value: validates + configures cgroup v2 `memory.max`
  - unsupported/unwritable cgroup capability: startup blocked deterministically

Launch observability and error model:
- `ServerInstance._log_launch_event(...)` emits structured launch events with context:
  - server identity/type
  - cwd
  - final argv
- expected launch event phases include:
  - `launch_attempt`
  - `launch_spawned` (includes PID returned)
  - `memory_limit_verify` or `memory_limit_verify_unavailable` (memory-limit launches)
  - `cpu_affinity_verify` or `cpu_affinity_verify_unavailable` (affinity-enabled launches)
  - `launch_success`
  - `launch_blocked` / `launch_failure` (with reason code)
- wrapper-policy triggers emit process-tree details when detected.
- affinity verification reads `/proc/<pid>/status` (`Cpus_allowed_list`) on Linux and logs the effective set when available.

Wrapper policy scaffolding:
- optional mode via env var `CRAFTY_WRAPPER_POLICY_MODE`:
  - `disabled` (default)
  - `audit`
  - `enforce`
- startup grace window via env var `CRAFTY_WRAPPER_GRACE_SECONDS` (default `5`, clamped to `1..30`)
- when enabled, launch ownership is inspected for fork-and-exit wrapper patterns before normal post-launch flow continues
- in `audit`/`enforce` mode, startup can be delayed up to the configured grace window while ownership is inspected
- affinity-enabled or memory-limit-enabled launches force enforcement of unsupported fork-and-exit wrapper shape (no warning-only mode for those cases)

## Process Model (Explicit)

- `ServerInstance.setup_server_run_command()` tokenizes `settings["execution_command"]` using `Helpers.cmdparse(...)`.
- `ServerInstance.start_server()` passes that argv list into `_launch_server_process(...)`, which performs the actual `subprocess.Popen(..., shell=False)` call.
- Crafty lifecycle state (`check_running`, `stop_server`, `kill`, crash detection, stats polling) is anchored to `self.process.pid`.
- Launch branch behavior in `start_server()`:
  - Unix + `minecraft-bedrock`: dedicated branch with `LD_LIBRARY_PATH` adjustment.
  - `steam_cmd`: dedicated branch with optional `env.json` merge logic.
  - other types (including `minecraft-java` and `hytale`): default launch branch.

What this means:
- Crafty does not launch through an implicit shell.
- Crafty does not guarantee the launched process is always the Minecraft JVM.
- For `minecraft-java` defaults created by `Controller.create_api_server`, the command is usually direct `java ... -jar ...`.
- Operators can still set `execution_command` to wrappers/scripts; if those wrappers fork and exit, Crafty can lose correct lifecycle ownership of the real game process.

Engineering consequence:
- Any feature targeting process-level controls (CPU affinity, ptrace/profiling hooks, cgroup placement) must define behavior when `execution_command` is not direct JVM exec.

## Stop Path

- `stop_threaded_server()` calls `stop_server()` and joins server thread.
- `stop_server()`:
  - removes crash watcher if configured
  - sends in-process stop command if configured (`send_command`)
  - else terminates process
  - waits up to `shutdown_timeout`, then force kills (`kill`) if needed
  - clears state (`cleanup_server_object`)
  - removes stats jobs

Force kill behavior (`kill()`):
- kills child processes recursively via `psutil`
- then kills parent process

## Restart Path

`restart_threaded_server(user_id)`:
- if not running -> start only
- if running -> stop, wait briefly, then start

Restart can be triggered from:
- API action command
- schedule command (`restart_server`)
- crash recovery path
- update/backup workflows (conditional)

## Crash Detection and Recovery

- Crash detection jobs are scheduled every 30s when enabled.
- `detect_crash()` checks process state:
  - if running: reset restart counter
  - if exited with ignored code: suppress crash handling
  - else: mark crashed and call `crash_detected()`
- `crash_detected()` optionally restarts server if crash detection is enabled.
- Restart attempts are capped by `restart_count` logic.

## Update Flow

- Trigger: `server_upgrade()` -> threaded update path (`threaded_jar_update`).
- Update flow can:
  - trigger backup first
  - stop server if running
  - download/update executable based on server type
  - restart server if it was running before update

Notable coupling:
- Update behavior depends on backup configuration existence and status.

## Backup Flow

- `server_backup_threader(backup_id, update=False)` orchestrates backup preconditions.
- Optional pre-backup command, optional shutdown, and threaded backup execution.
- `backup_server()` delegates core work to `BackupManager.backup_starter(...)`.
- If backup config requests shutdown and server was running, server is started again afterward.

## Restore Flow

- API restore endpoint calls `ServerInstance.server_restore_threader(...)`.
- Restore starter validates traversal/path assumptions and file naming format.
- `BackupManager.valid_restore_starter(...)` stops running server before restore.

Important:
- Restore does **not** automatically restart server after completion in the current path.

## Process and Monitoring State

Runtime state fields include:
- `self.process`
- `self.start_time`
- `self.is_crashed`
- `self.restart_count`
- `self.updating`

Stats collection uses `Stats._try_get_process_stats(self.process, self.check_running(), memory_capacity_bytes=...)`.

## Key Engineering Implications

- Most lifecycle paths converge to `start_server` for process creation. This is the critical insertion point for launch-time behavior changes.
- Stop/restart/crash/update/backup behavior shares mutable object state across threads; changes should preserve ordering and idempotence.
- Spawn syscall path is now centralized, but branch-specific launch setup still varies by server type.
- Process tracking correctness depends on launch command semantics; wrapper/forking commands are a correctness hazard for lifecycle and monitoring.
- Startup in wrapper audit/enforce mode can include grace-window delay while ownership checks run.

## Known Uncertainty

- Some edge paths rely on broad exception handling, making exact failure semantics partially implicit.
- Legacy import pathway (`Import3`) appears stale and may not align with current controller surface.
- Runtime behavior for every possible custom `execution_command` shape cannot be proven by static inspection alone; process-tree validation is required when introducing launch-time controls.
