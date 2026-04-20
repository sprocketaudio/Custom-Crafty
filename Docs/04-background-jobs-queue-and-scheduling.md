# 04. Background Jobs, Queueing, and Scheduling

## Purpose
This document explains how asynchronous and scheduled work is executed.

Primary file: `app/classes/shared/tasks.py` (`TasksManager`).

## Background Execution Components

`TasksManager` creates and owns:
- `scheduler` (`APScheduler` background scheduler)
- `schedule_thread` (`scheduler_thread`)
- `command_thread` (`command_watcher`)
- `log_watcher_thread`
- `realtime_thread`

Each `ServerInstance` also owns two schedulers:
- `server_scheduler` (runtime stats, crash checks, per-server update watcher)
- `dir_scheduler` (directory size and player cache polling)

## Command Queue Model

### Producers
Commands are queued via `ManagementController.queue_command()` and `send_command()`.

Sources include:
- API server action endpoints
- scheduler jobs that enqueue `queue_command` callbacks
- internal workflow triggers

### Consumer
`TasksManager.command_watcher()` continuously polls queue and executes one command at a time.

Match-based dispatch includes:
- start/stop/restart/kill
- backup
- executable update
- generic stdin command fallback (`svr.send_command(...)`)

Operational behavior:
- Queue is in-memory only.
- If process exits, queued commands are lost.
- There is no persistence or replay log for queue content.

## Scheduler Model

### Global scheduler (`TasksManager.scheduler`)
Schedules global periodic tasks and user-defined server tasks.

Important methods:
- `scheduler_thread()` initializes scheduler and loads DB schedules.
- `_add_scheduler_command_job(...)` maps schedule config -> `queue_command` job.
- `schedule_watcher(...)` handles completion bookkeeping and reaction child tasks.

Supported task patterns:
- fixed interval (`minutes`, `hours`, `days`)
- cron strings
- reaction tasks (triggered by parent schedule completion)

### Per-server schedulers (`ServerInstance`)
Server-specific jobs include:
- realtime stats polling
- persisted stats recording
- crash detection watcher
- update watcher
- directory size polling
- player cache updates

## Schedule Data Flow

1. API creates/updates schedule records in DB (`HelpersManagement`).
2. `TasksManager` builds APScheduler jobs from persisted records.
3. Job callback enqueues command payload into command queue.
4. `command_watcher` resolves server object and performs action.

## Reliability Notes

- `command_watcher` includes broad exception boundaries around some operations.
- Scheduler job IDs are string-based and manually managed.
- Some schedule type handling appears internally inconsistent with model typing (see debt doc).

## Performance Notes

- Queue consumer loop sleeps frequently (`time.sleep(1)`), which is simple but coarse.
- Realtime stats and process CPU calls can be non-trivial under high server counts.
- Many jobs are periodic and independent; cumulative polling load should be considered before adding new high-frequency jobs.

## Security/Operational Notes

- Queue payloads include command strings and action IDs; input validation is mostly upstream in API handlers.
- Because queue is central to process control, malformed payloads can impact operations broadly.

## Known Uncertainty

- Backpressure behavior under heavy queue load is not explicitly instrumented.
- There is no durable audit of queue item failures beyond logs.
