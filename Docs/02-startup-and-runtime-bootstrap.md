# 02. Startup and Runtime Bootstrap

## Purpose
This document traces application startup from process launch to steady state.

## Bootstrap Sequence (`main.py`)

Main startup behavior is in `main.py` under `if __name__ == "__main__":`.

### 1) Early environment checks
- Root/admin execution is blocked in `main.py` using `Helpers.check_root()`.
  - If elevated privileges are detected, process exits.
- Python version check enforces Python 3.9+.

Operational note:
- Docker wrapper (`docker_launcher.sh`) runs as root only long enough to switch execution to user `crafty`, which aligns with root-blocking behavior in `main.py`.

### 2) Logging/session setup
- `helper.ensure_logging_setup()` prepares writable paths and logs directory.
- `setup_logging()` loads `app/config/logging.json` if present.
- `helper.create_session_file()` enforces single active process semantics via session lock.
- startup launch capability probe runs via `helper.detect_launch_capabilities()` and logs:
  - host OS runtime value
  - whether CPU-affinity prerequisites are available (`taskset` path on Linux)
  - explicit reason when capability is unavailable (for example non-Linux host or missing `taskset`)

### 3) Database + migrations
- Main DB: SQLite (`helper.db_path`) initialized with WAL mode.
- Database proxy initialized (`database_proxy.initialize(database)`).
- Migrations executed via `MigrationManager.up()`.

### 4) Fresh install defaults
- `DatabaseBuilder.is_fresh_install()` determines first-run state.
- On fresh install, default admin credentials and baseline settings are created.

### 5) Controller graph construction
Constructed objects include:
- `FileHelpers`
- `ImportHelpers`
- `Controller` (which internally constructs subcontrollers)
- `TasksManager`
- `Import3`

`controller.set_project_root(APPLICATION_PATH)` is called to anchor path behavior.

### 6) Config reconciliation
- `controller.get_config_diff()` reconciles user config with master config defaults.
- This is an in-place config upgrade mechanism.

### 7) Webserver start
- `tasks_manager.start_webserver()` starts Tornado via `Webserver.run_tornado()` in a dedicated thread.
- TLS certs are created/ensured before bind.
- API and panel routes are registered.

### 8) Server object initialization
- `controller.servers.init_all_servers()` loads all defined servers.
- For each server, a `ServerInstance` is created and initialized.
- Autostart jobs are scheduled if enabled.

### 9) Long-running worker threads
`setup_starter()` triggers:
- scheduler startup (`tasks_manager.start_scheduler()`)
- host stats collection start
- internet connectivity check
- cache refresh and post-start tasks

Signal handlers (`SIGTERM`, `SIGINT`) route to graceful exit path.

## Runtime Composition After Startup

At steady state, the process contains:
- Tornado IOLoop thread
- scheduler and queue worker threads from `TasksManager`
- one `ServerInstance` per loaded server (each with own schedulers)
- per-running-server process and output reader thread

## Shutdown Path

Primary shutdown flow:
- signal handler in `main.py` -> `tasks_manager._main_graceful_exit()`
- removes session lock
- attempts to stop all running servers
- cleans temp files
- exits command loop/daemon loop

## Operational Considerations

- Startup does significant work in-process (migrations, cache refresh, controller init). Failures can abort full service startup.
- There is limited staged health signaling beyond logs/websocket updates.
- Because many subsystems are initialized before webserver is fully ready, startup ordering matters if modifying boot behavior.

## Known Uncertainty

- Some startup helper methods use broad exception handling; error boundaries are not always explicit in logs.
- No explicit readiness probe endpoint orchestration is visible in startup flow (outside generic API availability).
