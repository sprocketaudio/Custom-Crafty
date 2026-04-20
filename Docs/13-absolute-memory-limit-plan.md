# Per-Server Absolute Memory Limit Plan

## Document intent
This is a planning/specification document only. It defines how to add a true per-server absolute RAM limit with the same rigor used for CPU affinity.

## Current status (2026-04-18)
Implemented in code:
1. `Servers.memory_limit_mib` persisted with migration.
2. Create/PATCH API validation and superuser gating for `memory_limit_mib`.
3. Wizard + server settings UI fields for `memory_limit_mib`.
4. Launch capability probe includes `memory_limit` capability.
5. Launch path enforces fail-closed behavior when memory limit is configured but unsupported.
6. Linux cgroup v2 `memory.max` is configured per server and spawned PID is attached to that cgroup.
7. Per-server memory percent is normalized to allowed memory capacity (`used / allowed`), and capacity is exposed as `mem_capacity` / `mem_capacity_raw`.
8. Stats DB persists `mem_capacity_raw` for historical samples.

Still pending manual validation:
1. Full Linux runtime lifecycle smoke with actual cgroup write permissions in your deployment.
2. Operator verification pass for real process tree + cgroup membership on target host.

Primary target:
- Linux host runtime.

Out of scope for this phase:
- Cross-platform parity (Windows/macOS hard caps).
- Container-runtime redesign.
- Full QoS scheduling or memory pressure balancing across servers.

No partial rollout rule:
- Absolute memory limits must not be enabled for any production server until Phase RM0 through RM4 are complete and validated.

## 1) Problem statement
Current memory control is JVM-argument based (`-Xms`/`-Xmx`) and is not a hard process cap.
That is insufficient when the requirement is an absolute max memory budget per server process.

The panel needs:
1. A per-server absolute memory cap setting available at creation time and in server settings.
2. Runtime enforcement as an OS-level hard limit.
3. Per-server memory reporting normalized to allowed memory (like CPU now normalizes to allowed cores).
4. Existing host dashboard memory to remain host-wide totals.

## 2) Goals
1. Add a true absolute per-server RAM cap.
2. Keep JVM `-Xms`/`-Xmx` controls, but clearly label them as Java heap args.
3. Make per-server memory percent represent `used / allowed`.
4. Ensure all lifecycle starts use identical memory-limit enforcement.
5. Enforce deterministic failure when a configured hard cap cannot be applied.

## 3) Non-goals and anti-goals
1. Do not treat `-Xmx` as a hard cap.
2. Do not silently fall back from hard-cap mode to no-cap mode.
3. Do not implement shell-based hacks.
4. Do not broaden support to arbitrary wrapper behaviors.
5. Do not modify host-level memory cards/charts to server-scoped semantics.

## 4) Current architecture relevant to this feature
1. Server launch is centralized in `ServerInstance.start_server(...)` and converges through `_launch_server_process(...)` in `app/classes/shared/server.py`.
2. CPU affinity already uses a capability probe (`Helpers.detect_launch_capabilities`) called at startup (`main.py`) and strict launch-time failure semantics if configured but unsupported.
3. Per-server memory stats currently come from:
   - `Stats._get_process_stats(...)` in `app/classes/remote_stats/stats.py`:
     - `memory_usage_raw`
     - `memory_usage` (human-readable)
     - `mem_percentage` from `psutil.Process.memory_percent()` (host-relative)
4. Server stat snapshots persist to per-server stats DB (`app/classes/models/server_stats.py`) with `mem` and `mem_percent`.
5. Dashboard/server detail/metrics render `mem_percent` as percentage today.

Implication:
- Current memory percentages are not based on per-server allowed memory.
- A hard-cap feature requires both launch enforcement and stats/reporting normalization changes.

## 5) Final implementation decision
Chosen method:
1. Linux cgroup v2 `memory.max` enforcement per server.
2. Configure cgroup limit before spawn, then attach spawned PID to that cgroup immediately after spawn.

Reason for this decision:
1. cgroup v2 is the correct kernel primitive for hard memory caps.
2. It constrains full process memory footprint, not only JVM heap.
3. Existing `Popen(..., shell=False)` architecture can enforce this without shell wrapping or `preexec_fn`.
4. It aligns with the strict capability/failure approach already used by affinity.

Explicitly not chosen as primary enforcement:
1. `-Xmx` only (not absolute).
2. `RLIMIT_AS` / `prlimit` as hard-cap strategy for JVM.
3. `systemd-run` redesign as a first step.
4. Post-launch best-effort moves without deterministic failure.

## 6) Capability model and prerequisites
Required runtime prerequisites for hard-cap mode:
1. Linux host.
2. cgroup v2 memory controller available.
3. Writable delegated cgroup subtree for Crafty.
4. Ability to write `memory.max` and `cgroup.procs` in delegated subtree.

Startup capability probe:
1. Extend `Helpers.detect_launch_capabilities()` to include `memory_limit` capability status.
2. Log reasoned capability state once at startup, similar to `cpu_affinity`.

Launch-time guard:
1. If server has hard limit configured and `memory_limit.supported` is false, block start.
2. Emit user-visible error and structured launch log event.

## 7) Data model and API shape
## 7.1 Server config model
Add server-level field:
1. `memory_limit_mib` (integer, default `0` meaning disabled).

Keep existing CPU affinity field unchanged.

## 7.2 Server stats model
Add per-snapshot capacity field:
1. `mem_capacity_raw` (bytes) in per-server stats DB.

Rationale:
1. Historical percent must remain accurate even if limits change later.
2. Metrics chart percent can be derived consistently from each sample’s capacity.

## 7.3 API validation
Create and patch schemas should accept:
1. `memory_limit_mib` (optional, superuser-controlled).

Validation rules:
1. Integer only.
2. `0` allowed (disabled).
3. Non-negative only (current implementation does not enforce an upper bound).
4. Java `-Xmx` compatibility validation is not implemented in this phase.

## 8) UI/UX requirements
## 8.1 Wizard
1. Add absolute memory limit input (MiB/GiB display, stored as MiB).
2. Keep existing min/max heap fields.
3. Rename min/max labels to clearly indicate Java args:
   - JVM Min Heap (`-Xms`)
   - JVM Max Heap (`-Xmx`)
4. Include inline explanation that JVM fields are not host hard caps.

## 8.2 Server settings page
1. Add editable absolute memory limit field.
2. Keep execution command and JVM behavior intact.
3. Apply same client-side syntax/range guard style used by affinity.

## 8.3 Dashboard and detail pages
1. Host memory card stays host-wide total/percent (no change).
2. Per-server memory usage on dashboard:
   - Percent uses `used / allowed`.
   - Keep current `used` display in MB/GB after percent.
3. Server detail top stats:
   - Show memory as `used of allowed` (for example `2.1 GB of 4.0 GB`).

## 8.4 Metrics page
1. RAM percent line must represent percent of allowed memory at each sample.
2. RAM GB line remains used GB.

## 9) Reporting semantics (authoritative)
Define per-server memory capacity:
1. If hard cap enabled: configured cap bytes.
2. If hard cap disabled: effective host/container memory capacity.

Define per-server memory percent:
1. `mem_percent = round((memory_usage_raw / mem_capacity_raw) * 100, 2)`.
2. If capacity unavailable, use deterministic fallback and log warning.

Required payload fields:
1. `mem` (human-readable used memory).
2. `mem_raw` (used bytes).
3. `mem_percent` (normalized per allowed capacity).
4. `mem_capacity` (human-readable allowed memory).
5. `mem_capacity_raw` (allowed bytes).

## 10) Lifecycle coverage requirements
Hard-cap enforcement must apply to every launch path:
1. create then first start
2. manual start
3. manual restart
4. crash detection auto-restart
5. scheduled start/restart
6. update/redeploy restart paths
7. backup-triggered restart path

Constraint:
- Enforcement belongs in the centralized launch path only.

## 11) Security and operational safety
1. Keep all command execution as argv arrays with `shell=False`.
2. Superuser-only mutation for host-resource controls (absolute memory limit).
3. Validate bounds strictly server-side.
4. Fail closed when cap cannot be applied.
5. Prevent path traversal or arbitrary cgroup path injection:
   - cgroup path must be generated internally from server ID.
6. Log structured launch events:
   - requested limit
   - canonical applied limit
   - launch argv
   - PID
   - cgroup path
   - verification status

## 12) Reliability and performance considerations
1. OOM-kill behavior will be more likely under tight caps; this is expected.
2. Java native/off-heap/GC overhead means `-Xmx` must leave headroom under hard cap.
3. Limit changes over time require per-sample capacity persistence for accurate historical graphs.
4. If cap is too low, startup may fail or the process may be killed quickly.
5. Overly permissive caps can still cause host contention if many servers share host memory.

## 13) Failure semantics (deterministic)
1. Invalid config at save-time: reject request with validation error.
2. Config valid but host cannot enforce at runtime: block launch and notify user.
3. Enforcement configured but verification fails: mark launch as failed and log explicit reason.
4. Never silently downgrade to unlimited memory.

## 14) Phased plan
## RM0: capability and mechanism spike
1. Prove cgroup v2 memory enforcement works with current launcher model.
2. Prove PID ownership remains stable through exec helper.
3. Prove behavior across start/restart/crash restart.
4. Decide delegated cgroup root location and permissions model.

Exit criteria:
1. Verified process tree and cgroup membership.
2. Verified deterministic failure when prerequisites missing.

## RM1: schema, persistence, and migrations
1. Add `Servers.memory_limit_mib`.
2. Add per-server stats `mem_capacity_raw`.
3. Add migrations and rollback scripts.

Exit criteria:
1. Fresh install and migrated install both work.
2. Stats DB inserts/reads include new field without regressions.

## RM2: create/patch API and UI inputs
1. Wizard: add hard-limit input and relabel JVM min/max fields.
2. Server settings: add hard-limit input.
3. API create/patch: validate and persist.
4. Superuser permission enforcement for hard-limit field.

Exit criteria:
1. Valid values save.
2. Invalid values reject with explicit message.
3. Non-superuser cannot set hard limit.

## RM3: launch enforcement integration
1. Add memory-limit capability probe to startup diagnostics.
2. Integrate cgroup memory setup in centralized launch path.
3. Ensure strict launch block when configured limit cannot be applied.
4. Keep compatibility with existing CPU affinity flow.

Exit criteria:
1. Every launch path applies configured cap.
2. Launch logs include requested/applied cap and PID.

## RM4: stats normalization and runtime payloads
1. Compute per-server memory percent from allowed capacity.
2. Populate `mem_capacity` and `mem_capacity_raw` in runtime payloads.
3. Persist per-sample `mem_capacity_raw`.

Exit criteria:
1. Runtime and persisted stats reflect allowed memory semantics.
2. Historical percent remains correct after limit changes.

## RM5: UI reporting updates
1. Dashboard server memory percent uses normalized values.
2. Dashboard keeps used-memory value display after percent.
3. Server detail top memory displays `used of allowed`.
4. Metrics RAM% graph uses normalized history.

Exit criteria:
1. Host cards unchanged.
2. All per-server memory percentages are limit-aware.

## RM6: test matrix and observability
1. Unit tests for parsing/validation and normalization math.
2. Lifecycle integration tests for launch path convergence.
3. UI payload contract checks.
4. Structured logs and verification tooling documented.

Exit criteria:
1. Test suite coverage includes create/edit/start/restart/crash/schedule/update/backup restart.
2. Operators can verify applied limits at runtime quickly.

## RM7: rollout controls and operator docs
1. Add operator runbook for hard memory limits.
2. Document conservative defaults and recommended Java headroom.
3. Define rollback path per phase.

Exit criteria:
1. Production rollout checklist complete.
2. Rollback documented and tested.

## 15) Testing strategy
1. Unit:
   - limit validation bounds
   - JVM `-Xmx` cross-check logic (parseable commands)
   - normalized percent calculations
2. Integration:
   - launch with no limit
   - launch with valid limit
   - launch with unsupported host capability and configured limit (must fail)
   - restart/crash/scheduled/update/backup restart with enforced limit
3. UI/API:
   - wizard create payload includes hard limit
   - server settings patch updates hard limit
   - non-superuser blocked from changing hard limit
4. Metrics:
   - dashboard server memory percent reflects allowed capacity
   - detail page shows `used of allowed`
   - metrics RAM% reflects allowed capacity over time

## 16) Open decisions requiring spike confirmation
1. Final delegated cgroup root strategy in your deployment model.
2. Swap policy (`memory.swap.max`) default behavior.
3. How strict to be when Java command is custom and `-Xmx` cannot be parsed.

## 17) Recommended next step
Execute RM0 as a short technical spike and lock the cgroup enforcement mechanism before touching schema/UI.
