# Per-Server CPU Affinity Implementation Plan

## Document Intent
This started as a planning document and now also tracks implementation status and remaining work.
It defines the target design for per-server CPU affinity in this fork and records what is complete.

Execution order:
- complete pre-work gate phases in `Docs/10-affinity-prework-gate-plan.md` first
- then execute feature phases in this document

No partial rollout rule:
- do not enable CPU affinity for any server until pre-work phases PW1 through PW4 are complete and validated.

Primary target:
- Linux hosts managing Minecraft server processes through Crafty

Hard runtime requirement for this phase:
- Linux host with `util-linux` package providing `taskset`

Out of scope for this phase:
- CPU quota/shares (`cpu.max`, cgroup quotas)
- NUMA-aware scheduling policy
- automatic global core allocator

Implementation status snapshot (2026-04-17):
- Feature Phase 1 completed:
  - `Servers.cpu_affinity` field added (`app/classes/models/servers.py`)
  - DB migration added (`app/migrations/20260417_cpu_affinity.py`)
  - affinity parser/canonicalizer added (`app/classes/helpers/cpu_affinity.py`)
  - server patch API canonicalizes/validates `cpu_affinity`
  - startup capability probe logs CPU-affinity prerequisite status
- Feature Phase 2 completed:
  - superuser server config UI includes `cpu_affinity` input with examples/requirements hint
  - client-side syntax-level validation added before PATCH submit
  - failed-server panel fallback mapping includes `cpu_affinity`
- Feature Phase 3 completed:
  - centralized launch command resolver applies affinity prefix (`taskset --cpu-list ...`) when configured
  - launch-time host capability checks block startup deterministically when affinity cannot be applied
  - affinity-enabled launches enforce unsupported fork-and-exit wrapper shape failure
- Feature Phase 4 completed:
  - lifecycle convergence guardrail tests added for launcher and restart/recovery flows
  - launch path structural tests assert all spawn branches in `start_server` route through `_launch_server_process(command=launch_command)`
  - runtime observability now logs effective CPU set from `/proc/<pid>/status` (`Cpus_allowed_list`) when available
- Feature Phase 5 completed:
  - operator runbook published (`Docs/12-cpu-affinity-operator-runbook.md`)
  - metric caveat and overlap guidance linked and clarified in risk documentation

---

## 1) Problem Statement
Operators need per-server CPU core pinning (example: `0-3`, `4,6,8,10`) so managed servers run on controlled host cores and contention is reduced.

Current state:
- affinity field exists in `Servers` model (`cpu_affinity`)
- affinity syntax validation/canonicalization exists in server patch API (superuser path)
- startup capability detection exists and logs host affinity prerequisites
- affinity enforcement is active in `ServerInstance.start_server` through centralized launch command resolution
- affinity-enabled launches attempt effective-set verification logging after spawn (`cpu_affinity_verify`)

Required outcome:
- affinity is applied at launch to the actual tracked server process model
- behavior is consistent across all lifecycle restart paths
- failure behavior is deterministic and operator-visible
- implementation target includes all server modes that use the shared launch path (not java-only logic)

---

## 2) Final Implementation Decision (for this codebase)

Chosen method for Phase 1:
- prepend launch command with `taskset --cpu-list <canonical_mask>` and keep `Popen(..., shell=False)`

Why this is the selected method:
- fits current `ServerInstance.start_server` launch architecture without introducing `preexec_fn` thread-safety risk
- applies affinity before workload execution
- keeps command execution shell-safe (argv list, not shell string)
- operationally simple to verify with `taskset -pc` and `/proc/<pid>/status`

Explicitly not chosen for Phase 1:
- post-spawn `os.sched_setaffinity(pid, ...)` as primary path (race window)
- `preexec_fn` affinity in multithreaded parent (unsafe pattern)
- wrapper binary/script as mandatory dependency (more moving parts than needed now)
- cgroup/systemd redesign (too large for this feature phase)

Additional policy decisions for Phase 1:
- wrapper commands that fork/daemonize and let the parent exit are explicitly unsupported for affinity-enabled servers
- this unsupported command shape is enforced as a startup failure (not a warning-only behavior)
- host affinity capability (`taskset` availability) is detected and logged once at startup, then reused at runtime
- affinity enforcement is implemented once in the centralized launcher path and applies to all server types by design (branch-specific env handling remains unchanged)

---

## 3) Goals

- Add per-server affinity config persisted in DB.
- Validate affinity syntax and host applicability.
- Enforce affinity in one centralized launch path.
- Ensure restart/crash/schedule/update/backup restart paths inherit enforcement automatically.
- Use strict, deterministic failure semantics.

## 4) Non-Goals

- Cross-platform parity for affinity behavior.
- Automatic conflict resolution of overlapping core assignments.
- Startup/steady-state dual affinity profiles (future phase).

---

## 5) Current Architecture Relevant to Affinity

### 5.1 Launch and lifecycle convergence
Primary launch function:
- `ServerInstance.start_server(...)` in `app/classes/shared/server.py`

Spawn syscall callsite today:
- centralized in `ServerInstance._launch_server_process(...)` (single `subprocess.Popen(...)` location)
- `start_server(...)` branches call this helper with resolved `launch_command`

Paths converging to spawn:
- autostart: `do_server_setup -> run_scheduled_server -> run_threaded_server`
- command queue start/restart: `TasksManager.command_watcher`
- crash recovery: `detect_crash -> crash_detected -> run_threaded_server`
- update restart: `threaded_jar_update`
- backup-triggered restart: `backup_server` (`conf["shutdown"]` + `was_running`)

### 5.2 Process model constraints (critical)
- Crafty tracks `self.process.pid` for lifecycle control and stats.
- Popen argv comes from `settings["execution_command"]` parsed by `Helpers.cmdparse(...)`.
- For Java servers created via defaults, command is usually direct JVM invocation.
- Operator-custom `execution_command` can still be wrapper/script-based.
- If wrapper forks and exits, Crafty lifecycle ownership is already fragile (independent of affinity).

Implication:
- affinity feature must preserve Crafty's existing PID ownership assumptions and enforce unsupported wrapper patterns for affinity-enabled servers.

Supported command shapes when affinity is configured:
- direct executable launch (for example `java ... -jar ...`)
- wrapper that performs `exec` and keeps a stable lifecycle PID

Unsupported command shapes when affinity is configured:
- wrappers that fork/daemonize and exit parent while child continues

Enforcement direction:
- if parent PID exits during startup grace window and child process continues, treat launch as unsupported command shape and fail startup.

Startup grace-window tuning notes:
- this window must be explicit and configurable (for example 3 to 10 seconds) to avoid hidden heuristics.
- default recommended value: `5s` (tunable per deployment if false positives/negatives appear).
- detection should be based on process state checks (`poll()` plus process-tree inspection), not sleep-only assumptions.
- if parent exits but no surviving child exists, treat as normal failed launch, not wrapper-shape violation.
- if parent exits and a surviving child exists, treat as unsupported wrapper command shape when affinity is configured.
- threshold should be tuned using real production-style commands to avoid false positives for fast launcher behaviors.

Current pre-work scaffolding implementation:
- env `CRAFTY_WRAPPER_POLICY_MODE` supports `disabled` (default), `audit`, `enforce`
- env `CRAFTY_WRAPPER_GRACE_SECONDS` sets grace window (default `5`, clamped to `1..30`)
- these controls are pre-affinity scaffolding and will be integrated with affinity enablement gates in later phases

---

## 6) Implemented Approach (Phase 1-4)

## 6.1 Launch centralization
`ServerInstance.start_server` now routes spawn through one helper.

Target shape:
- `_launch_process(command: list[str], cwd: str, env: dict | None) -> subprocess.Popen`

Result:
- prevents partial affinity coverage across branch-specific launch setup
- keeps one spawn syscall point for future startup/steady affinity extensions

## 6.2 Affinity application at launch
When server has non-empty affinity config:
1. Parse + canonicalize affinity string.
2. Validate against effective host CPU set.
3. Build launch argv as:
   - `["taskset", "--cpu-list", canonical_affinity, *original_command]`
4. Launch with `Popen(argv, shell=False, ...)`.

When affinity config is empty:
- use existing launch argv without `taskset`.

## 6.3 Host capability detection (startup guardrail)
At service startup:
1. Detect OS capability (`linux` required for this feature phase).
2. Detect `taskset` once using `shutil.which("taskset")`.
3. Persist capability in runtime state (for example controller capability flags).
4. Emit startup log with explicit capability status and reason.

Runtime behavior:
- affinity-enabled launch must check cached capability before spawn and fail deterministically if unavailable.
- startup capability detection does not replace launch-time validation; launch still validates effective CPU set and command shape.

Operator-facing requirement text:
- per-server CPU affinity feature requires Linux and `util-linux` (`taskset`).

---

## 7) Validation Rules

Accepted syntax:
- single CPU: `3`
- list: `1,4,7`
- range: `2-5`
- mixed: `0-3,8,10-12`

Reject conditions:
- empty segments (e.g., `1,,2`)
- non-numeric tokens
- negative values
- inverted ranges (`7-3`)
- duplicates after expansion
- IDs outside effective allowed CPU set

Effective CPU set source (Linux):
- `os.sched_getaffinity(0)` for runtime-aware validation (cpuset/container aware)

Canonicalization:
- sorted unique IDs, compacted to range string for storage/logging

Example:
- input `4,2-3,3,2` -> canonical `2-4`

---

## 8) Deterministic Failure Semantics (Final)

Policy:
- no silent fallback when affinity is configured

Behavior:
1. Invalid affinity in API request:
   - reject request with 400 and structured error
2. Affinity configured but host cannot apply (non-Linux, missing `taskset`, runtime CPU-set mismatch):
   - start operation fails
   - process is not launched
   - log critical operator-visible error
   - surface start failure to websocket/API client
3. Affinity configured but launch command shape is unsupported (fork-and-exit wrapper):
   - start operation fails
   - log explicit unsupported command shape error
   - surface start failure to websocket/API client
4. Empty affinity config:
   - normal legacy behavior

Rationale:
- silent fallback creates false safety assumptions and defeats operator intent

---

## 9) Security Considerations

- Keep `Popen` argv list usage; never build shell command strings.
- Restrict affinity config edits to privileged users (superuser-level server config path).
- Validate both at API boundary and launch boundary (defense in depth).
- Treat affinity as operationally sensitive: malicious low-privilege edits can induce contention DoS.
- Log requested affinity, canonical affinity, and apply result.
- Log effective post-launch CPU set read from runtime state (for example `taskset -pc <pid>` or `/proc/<pid>/status` `Cpus_allowed_list`) for operator debugging.

---

## 10) Performance and Reliability Considerations

### 10.1 JVM-specific caution
- Minecraft Java workloads are multithreaded (GC/JIT/network/async).
- overly narrow pinning can increase pauses and degrade MSPT/TPS.
- recommendations:
  - benchmark under realistic load
  - avoid over-constraining larger modded servers

### 10.2 Overlap risk
- overlapping affinity masks across busy servers can nullify isolation goals.
- this is a serious operational risk even if syntax is valid.
- phase 1 should at least warn when configured mask overlaps another running server mask (advisory warning; not hard block).

Planned progression:
- phase 1: soft warning
- later: optional hard-block policy via config flag (for example `affinity_enforce_no_overlap=true`)

### 10.3 Reserved host cores guidance
- avoid pinning busy game servers onto cores heavily used by OS/control-plane workloads.
- practical default guidance: keep at least one or two cores (often `0` and optionally `1`) reserved for host, panel, and container runtime overhead.
- this should evolve into explicit configurable reserved-core policy (for example `reserved_host_cores`) with validation warnings when intersected.

### 10.4 Monitoring caveat
- current server CPU metric normalization uses process CPU capacity when available (`len(process.cpu_affinity())`).
- fallback remains total host core count where process affinity is unavailable on the runtime platform.
- docs and operator runbooks must call out which denominator is active during incident/debug workflows.

Follow-up recommendation:
- expose the active CPU denominator in panel/API diagnostics to reduce operator confusion.

---

## 11) Lifecycle Coverage Requirements

Affinity must apply to every spawn path:
- manual start
- manual restart
- scheduled start/restart
- crash recovery restart
- update-driven restart
- backup shutdown restart
- any future restore-start path

Design rule:
- every spawn path must call one launch helper that applies affinity consistently.

---

## 12) Required Changes by Layer

## 12.1 Persistence/model
- add `cpu_affinity` field to `Servers` model (`app/classes/models/servers.py`)
- add migration under `app/migrations` with default empty string

## 12.2 API/schema
- extend server patch schema (`app/classes/web/routes/api/servers/server/index.py`)
- keep affinity writable only through superuser-capable schema branch
- return deterministic schema/validation errors

Optional:
- add create-time affinity field in `new_server_schema` (`app/classes/web/routes/api/servers/index.py`) or defer to patch-only first

## 12.3 UI
- add affinity input field in `app/frontend/templates/panel/server_config.html`
- include affinity in PATCH payload
- ensure failed-server rendering paths tolerate field presence (`panel_handler.py` fallback server objects)

Recommended UX polish in this phase:
- placeholder example: `0-3,6,8`
- inline client-side validation feedback (syntax-level) before submit
- tooltip/help text:
  - "Pins this server to specific CPU cores."
  - "Requires Linux + taskset."

Future UX enhancement:
- overlap warning banner when configured mask intersects other active servers

## 12.4 Runtime/launcher
- refactor duplicated launch branches in `ServerInstance.start_server`
- add startup capability probe/caching for affinity support (`taskset` + OS)
- add affinity parse/apply/logging in centralized launch helper
- enforce unsupported wrapper command-shape failure for affinity-enabled servers

## 12.5 Clone/import
- define explicit clone behavior (copy affinity vs clear affinity)
- ensure import-created servers default to empty affinity unless explicitly set

---

## 13) Process Tree and PID Correctness Validation (Required)

Before implementation is declared complete, verify:
- PID tracked by Crafty is the intended lifecycle owner
- affinity is applied to that PID
- child process behavior under wrapper commands is understood and documented

Minimum checks on Linux host:
1. `taskset -pc <pid>`
2. `grep Cpus_allowed_list /proc/<pid>/status`
3. `cat /proc/<pid>/task/<pid>/children`
4. `ps -o pid,ppid,comm,args` (or equivalent) for parent/child ownership inspection

Acceptance rule:
- for supported command shapes, tracked PID and operational server process model must stay aligned.
- for unsupported command shapes, startup must fail deterministically rather than continue in degraded ownership mode.

---

## 14) Runtime Verification Strategy (Operator/Debug)

For a running server with configured affinity:
1. read PID from panel/log/runtime object
2. run `taskset -pc <pid>`
3. confirm `/proc/<pid>/status` contains expected `Cpus_allowed_list`
4. if wrapper command is used, inspect child process tree and confirm expected ownership

Current runtime observability:
- structured launch events include final `argv`, spawned `pid`, and affinity details
- when affinity is active, runtime emits:
  - `cpu_affinity_verify` with canonical and effective CPU list (from `/proc/<pid>/status`) when readable
  - `cpu_affinity_verify_unavailable` when effective set cannot be read

Future enhancement:
- expose effective affinity directly in panel/API debug surfaces (not only logs)

---

## 15) Pre-Implementation Spike Findings and Gaps

Spike environment used for preliminary validation:
- Linux kernel `6.6.87.2-microsoft-standard-WSL2`
- WSL distro: `docker-desktop`
- `taskset` present (`/usr/bin/taskset`)

What was validated in a Linux shell spike (WSL `docker-desktop` distro):
- `taskset --cpu-list` can apply restricted CPU lists to launched process
- affinity observed in `/proc/<pid>/status` `Cpus_allowed_list`
- child process inherited affinity in a wrapper-parent scenario
- wrapper can exit while child continues, showing why command shape matters for PID ownership

Observed command patterns:
1. Direct command pinning:
   - `taskset --cpu-list 0 sleep 30 &`
   - observed `Cpus_allowed_list: 0` on tracked PID
2. Wrapper with resident parent and child:
   - `taskset --cpu-list 2 sh -c 'sleep 30 & wait' &`
   - observed parent and child both constrained to CPU `2`
3. Wrapper that forks child then exits:
   - `taskset --cpu-list 3 sh -c 'sleep 30 & echo $! >/tmp/aff_child_pid' &`
   - observed parent process exited quickly while child remained pinned to CPU `3`
   - confirms lifecycle tracking risk for fork-and-exit wrappers

Remaining validation gaps after implementation:
- validate on actual deployment host/distribution (not only WSL docker-desktop)
- validate against real Crafty-launched Minecraft Java process command shapes
- validate non-default runtime branches (`minecraft-bedrock`, `steam_cmd`, `hytale`) under affinity-enabled starts

---

## 16) Testing Strategy

## 16.1 Unit tests
- parser/canonicalizer valid/invalid matrix
- out-of-range and duplicate handling
- canonical string generation

## 16.2 Integration tests
- start/restart/crash/scheduled/update/backup restart all apply affinity
- empty affinity keeps baseline behavior
- configured affinity + unsupported host fails deterministically

## 16.3 Manual operational tests
- verify applied affinity with `/proc` and `taskset -pc`
- verify logs show requested/canonical/applied values
- verify CPU metrics interpretation caveat is documented for operators
- prioritize default-branch (`minecraft-java`) lifecycle validation first when resources are constrained; treat other server-mode runtime coverage as explicit follow-up risk work

---

## 17) Phased Implementation Plan

Precondition gate:
- PW0 to PW4 in `Docs/10-affinity-prework-gate-plan.md` must be complete
- no server-level affinity enablement before PW1 to PW4 completion (no partial rollout)

Current readiness decision for this fork:
- pre-work gate is marked GO in `Docs/10-affinity-prework-gate-plan.md`
- lifecycle smoke is validated on `minecraft-java` path
- non-default branch runtime validation (`minecraft-bedrock`, `steam_cmd`, `hytale`) is explicitly deferred risk, not an implicit assumption
- current implementation progress: Feature Phases 1 through 5 complete

Feature Phase 0: finalize host spike on deployment environment
- verify method and PID ownership against real commands
- verify unsupported wrapper detection thresholds (startup grace window) on real server commands

Feature Phase 1: data and validation
- add DB field + migration
- add parser/canonicalizer + tests
- extend API schema validation
- add startup capability detection (`taskset` presence + OS gate) and capability logging

Feature Phase 2: UI and config propagation
- add server config field and payload wiring
- ensure fallback render paths support new field

Feature Phase 3: launcher refactor and affinity enforcement
- centralize launch helper
- integrate `taskset` prefix and strict failure behavior
- enforce unsupported wrapper command-shape failure behavior
- add structured logs and websocket error surfacing

Feature Phase 4: lifecycle coverage hardening
- verify all spawn paths route through helper
- add integration coverage for restart/recovery flows

Feature Phase 4 evidence (2026-04-17):
- tests added:
  - `tests/classes/shared/test_server_launch_affinity.py`
  - `tests/classes/shared/test_server_lifecycle_launch_paths.py`
- targeted execution:
  - `.venv\Scripts\python.exe -m pytest tests\classes\helpers\test_cpu_affinity.py tests\classes\helpers\test_cmdparse.py tests\classes\shared\test_server_launch_affinity.py tests\classes\shared\test_server_lifecycle_launch_paths.py -q`
  - result: `38 passed in 0.73s`

Feature Phase 5: docs and operations
- publish operator verification runbook
- document metric caveats and overlap guidance

Feature Phase 5 evidence (2026-04-17):
- runbook added:
  - `Docs/12-cpu-affinity-operator-runbook.md`
- risk documentation updated:
  - `Docs/07-security-performance-and-operational-risks.md`
  - `Docs/README.md`

---

## 18) Future Extensions

- startup-burst affinity vs steady-state affinity
- optional CPU quota support (cgroup v2)
- optional overlap hard-block policy
- reserved-host-cores policy with explicit validation
- affinity denominator visibility in panel/API
- optional overlap detection/allocation assistance UI
- optional API/UI preflight validator:
  - validate affinity syntax and host applicability without starting the server

