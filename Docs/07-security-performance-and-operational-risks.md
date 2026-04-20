# 07. Security, Performance, and Operational Risks

## Purpose
This document highlights the most relevant engineering risks in current architecture.

## Security-Sensitive Areas

### 1) API request protection model
Files:
- `app/classes/web/base_handler.py`
- `app/classes/web/base_api_handler.py`

Observed behavior:
- API routes disable XSRF checks (`BaseApiHandler.check_xsrf_cookie` is a no-op).
- CORS default allows any origin (`Access-Control-Allow-Origin: *`).

Risk:
- Token-bearing cross-origin usage requires strict token hygiene and endpoint auth correctness.

### 2) Command/process execution surfaces
Files:
- `app/classes/shared/server.py`
- `app/classes/helpers/helpers.py` (`cmdparse`)

Observed behavior:
- server launch uses `Popen(list, shell=False)` (good baseline).
- launch command originates from DB-configured `execution_command`.

Risk:
- weak validation of command semantics can still cause dangerous runtime behavior even without shell invocation.

### 3) Filesystem traversal and restore/import operations
Files:
- `app/classes/helpers/helpers.py` (`validate_traversal`)
- `app/classes/shared/backup_mgr.py`
- `app/classes/shared/server.py` restore flow

Observed behavior:
- explicit traversal checks exist in important paths.
- some APIs warn that helper methods do not perform traversal checks and must be guarded by caller.

Risk:
- omission by future callers can reintroduce traversal vulnerabilities.

### 4) Secrets and auth
Files:
- `app/classes/shared/authentication.py`
- `app/classes/models/management.py`

Observed behavior:
- API/cookie secrets stored in DB settings row.
- JWT validation includes token issuance time and revocation window (`valid_tokens_from`).

Risk:
- broad exception handling around auth can obscure failure reasons and troubleshooting.

### 5) Privilege model
Files:
- server/role/crafty permissions handlers and controllers

Observed behavior:
- many routes perform explicit permission checks.

Risk:
- permission checks are scattered at handler level; consistency must be maintained manually.

## Performance-Sensitive Areas

### 1) Process stats polling
Files:
- `app/classes/shared/server.py` (`realtime_stats`, `record_server_stats`)
- `app/classes/remote_stats/stats.py`

Observed behavior:
- per-process CPU reads call `cpu_percent(interval=0.5)`.
- frequent polling jobs run per active server.

Risk:
- cumulative overhead grows with server count.
- CPU percentage is normalized by process CPU capacity when available (`len(process.cpu_affinity())`).
  - Fallback is host core count when process affinity is unavailable on the runtime platform.
- Per-server memory percentage is normalized by allowed memory capacity (`memory_limit_mib` when configured, otherwise host/container total).
  - Host dashboard memory card remains host-wide memory usage and is intentionally not server-scoped.

### 2) Console output processing
File:
- `ServerOutBuf.check` in `app/classes/shared/server.py`

Observed behavior:
- reads stdout one character at a time.

Risk:
- syscall-heavy behavior under high console throughput.

### 3) File operations in main process
Files:
- backup/import/file helper routines

Observed behavior:
- large archive and file operations can run in app process/threads.

Risk:
- heavy I/O may affect responsiveness if thread scheduling/contention worsens.

## Operational Risks

### 1) In-memory command queue only
File:
- `TasksManager.command_watcher` (`app/classes/shared/tasks.py`)

Risk:
- queued commands are not durable across process crash/restart.

### 2) Threaded mutable state
Files:
- `ServerInstance` lifecycle methods in `app/classes/shared/server.py`

Risk:
- race-prone state transitions if multiple triggers overlap.

### 3) Startup dependency chain
File:
- `main.py`

Risk:
- migration/config/bootstrap failures block service startup.

### 4) Broad exception handling
Observed across lifecycle and helper code.

Risk:
- latent defects may be logged but not surfaced in structured error contracts.

### 5) Affinity overlap and contention (when affinity is introduced)
Risk:
- overlapping core sets across multiple busy servers can erase isolation benefits and increase tail latency.
- accidental over-concentration (many servers pinned to same cores) is an operator-induced denial-of-service pattern.

Required operator guidance:
- treat affinity assignment as capacity planning, not just syntax configuration.
- document core-assignment policy (reserved cores, allowed overlap policy, emergency fallback policy).
- unless there is a strong reason otherwise, keep at least one or two host cores (often including core `0`) unassigned to busy Minecraft servers.
- use `Docs/12-cpu-affinity-operator-runbook.md` for rollout/verification/rollback procedure.

### 6) JVM behavior under hard pinning (Minecraft Java)
Risk:
- Java workloads use many threads (GC, JIT, networking, async tasks).
- overly narrow affinity sets can increase GC pause pressure and tick jitter.

Operator guidance:
- avoid aggressive single-core pinning for larger modded servers.
- validate MSPT/TPS and GC behavior under real load after any affinity change.

Telemetry follow-up:
- expose CPU denominator (effective allowed cores) in UI/API to make normalization basis explicit during debugging.

## Practical Safeguards for Future Changes

- Keep critical lifecycle behavior centralized.
- Add explicit logs for state transitions and failure causes.
- Add tests for negative paths, not only happy paths.
- Treat DB schema/config fields as privileged surfaces.
- Validate and canonicalize all operator-provided runtime controls.
- When adding host-resource controls, include runtime verification commands and deterministic failure semantics in docs.
