# 12. CPU Affinity Operator Runbook

## Purpose
This runbook defines how to safely operate per-server CPU affinity in this deployment.
It is operational guidance for live usage, not implementation design.

## Scope
- Applies to Crafty-managed server launches that route through `ServerInstance.start_server` in `app/classes/shared/server.py`.
- Applies to all server modes that use the shared launcher path (`minecraft-java`, `minecraft-bedrock`, `steam_cmd`, `hytale`).
- Affinity behavior in this phase is Linux-only and requires `taskset` (util-linux).

## Preconditions
Before enabling affinity on any server:
1. Pre-work and feature phases through Phase 4 must be complete.
2. Host must be Linux and have `taskset` available in PATH.
3. You must have a core assignment plan (including host-reserved cores).
4. You must accept current telemetry caveat:
   - server CPU% is normalized to the process allowed CPU set when affinity data is available.
   - fallback behavior uses host core count if process affinity cannot be read on the runtime platform.

## Affinity Syntax
Accepted examples:
- `0-3`
- `4,6,8,10`
- `2-5,9-11`

Behavior notes:
- values are canonicalized server-side before persistence.
- invalid or out-of-range values are rejected.
- empty value means affinity is disabled for that server.

## Rollout Strategy (Recommended)
Use a controlled rollout:
1. Enable affinity on one non-critical server first.
2. Restart and verify effective affinity.
3. Observe stability and performance under expected load.
4. Expand to additional servers in stages.

Do not apply broad affinity changes to all servers at once.

## Per-Server Change Procedure
1. Set `cpu_affinity` in server config (superuser path).
2. Save config.
3. Restart server from panel.
4. Verify launch and effective affinity (commands below).
5. Record assignment in your operations tracker.

## Verification Procedure (Linux)
Get the server PID from launch logs (event `launch_spawned`) or runtime process view.

Run:
```bash
taskset -pc <PID>
grep Cpus_allowed_list /proc/<PID>/status
cat /proc/<PID>/task/<PID>/children
ps -o pid,ppid,comm,args -p <PID>
```

Expected:
- `taskset -pc` and `Cpus_allowed_list` match configured canonical affinity.
- tracked PID is stable lifecycle owner for expected command shape.
- if wrapper policy triggers, logs include detected process tree details.

## Launch Event Signals to Watch
`start_server` emits structured `launch_event` records.

Key events:
- `launch_attempt`
- `launch_spawned`
- `cpu_affinity_verify` or `cpu_affinity_verify_unavailable`
- `launch_success`
- failure events:
  - `launch_blocked` with reasons such as:
    - `invalid_cpu_affinity`
    - `cpu_affinity_unsupported`
    - `cpu_affinity_taskset_missing`
  - `launch_failure` with reasons such as:
    - `unsupported_wrapper_shape`
    - `spawn_exception`
    - `early_exit_after_spawn`

## Deterministic Failure Semantics
When `cpu_affinity` is configured, startup is blocked if affinity cannot be safely applied.

There is no silent fallback to unpinned launch for configured affinity.

Operator impact:
- A misconfigured affinity value or unsupported host/tooling state will prevent server start.
- Corrective action is required before retry.

## Overlap and Capacity Guidance
Affinity overlap is allowed in this phase but operationally risky.

Guidance:
1. Maintain a per-host core allocation map.
2. Reserve host/control-plane cores (commonly include core `0`, optionally `1`).
3. Avoid pinning multiple high-load servers to the same small core set.
4. Re-check overlap after adding/removing servers or changing host topology.

Minimum manual check:
- compare configured canonical masks across active servers before each rollout batch.

## JVM/Minecraft Guidance
Minecraft Java processes are multithreaded (GC/JIT/network/async tasks).

Avoid:
- overly narrow pinning on large modded servers
- assuming single-core pinning improves performance universally

Validate after changes:
- MSPT/TPS under representative load
- GC pause behavior
- restart/crash-recovery behavior

## Metrics Interpretation Caveat
Current CPU usage metric for server processes uses:
- preferred denominator: number of CPUs allowed to the process (`process.cpu_affinity()` length)
- fallback denominator: host CPU count (`psutil.cpu_count()`)

Use additional signals for decisions:
- MSPT/TPS and player experience
- OS-level per-process CPU and affinity checks
- launch event verification logs

## Rollback Procedure
If an affinity change causes instability:
1. Set server `cpu_affinity` to empty.
2. Restart server.
3. Confirm normal launch without affinity prefix.
4. Re-evaluate assignment plan before re-enabling.

If startup is blocked due to affinity:
1. Inspect `launch_event` reason code.
2. Correct config/tooling/host issue.
3. Retry start.

## Known Limitations (Current Phase)
- no automatic global core allocator
- no hard overlap enforcement
- no startup-burst vs steady-state split
- non-default server-mode runtime affinity coverage is still an explicit follow-up validation area

## Escalation Triggers
Escalate before broader rollout if any occur:
- frequent `unsupported_wrapper_shape` in expected commands
- repeated `cpu_affinity_verify_unavailable` on Linux hosts where `/proc` should be readable
- unexpected PID churn after launch
- sustained performance regression after pinning despite no overlap
