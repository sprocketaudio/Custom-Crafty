# 00. Runtime Flow Diagram

## Purpose
This is the canonical one-page mental model for how a server action becomes a host process launch.
Use this as the first reference before changing lifecycle or launch behavior.

## Canonical Action Flow (UI/API to Process)

```mermaid
flowchart LR
    UI[Panel UI / API Client]
    API[Tornado Route Handler<br/>app/classes/web/routes/api/...]
    MGMT[ManagementController.send_command<br/>app/classes/controllers/management_controller.py]
    Q[(In-memory command_queue)]
    TW[TasksManager.command_watcher<br/>app/classes/shared/tasks.py]
    SI[ServerInstance methods<br/>app/classes/shared/server.py]
    SS[ServerInstance.start_server]
    POPEN[subprocess.Popen(..., shell=False)]
    PROC[OS Process Tree]

    UI --> API --> MGMT --> Q --> TW --> SI --> SS --> POPEN --> PROC
```

Equivalent text flow:
- `UI -> API -> Controller -> Queue -> Task Worker -> ServerInstance -> Popen -> Host process`

## Canonical Config Flow (UI/API to Runtime Settings)

```mermaid
flowchart LR
    UI[Server Config Form]
    PATCH[PATCH /api/v2/servers/{id}]
    VALIDATE[JSON schema + permission checks]
    MODEL[Servers model row update]
    SAVE[Peewee save]
    REFRESH[ServersController.update_server<br/>ServerInstance.update_server_instance]
    RUNTIME[Runtime settings reloaded in ServerInstance]

    UI --> PATCH --> VALIDATE --> MODEL --> SAVE --> REFRESH --> RUNTIME
```

Equivalent text flow:
- `UI -> PATCH handler -> schema/perm checks -> Servers table -> server instance refresh -> next runtime action`

## Process Ownership Notes (Critical for Affinity and Monitoring)

- Crafty launches managed servers via `subprocess.Popen(list_args, shell=False)` in `ServerInstance.start_server`.
- Crafty tracks `self.process.pid` as the server PID for stats, stop/kill, crash detection, and restart logic.
- The tracked PID is for the executable in `execution_command` after `Helpers.cmdparse(...)` tokenization and optional Java path substitution.
- This is not guaranteed to always be the JVM binary:
  - default Minecraft Java creation paths usually generate `java ... -jar ...`
  - operators can change `execution_command` to wrappers/scripts
  - if a wrapper forks and exits, Crafty will track the wrapper PID lifecycle, not a detached child

## Invariants to Preserve

- All lifecycle paths that start a process must converge to one launch path.
- Queue remains the central orchestration point for user/scheduler start/stop/restart actions.
- Runtime behavior must remain deterministic even under concurrent thread activity.
