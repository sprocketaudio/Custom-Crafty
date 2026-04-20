# 08. Fragility and Technical Debt

## Purpose
This document captures known fragile areas and debt relevant to maintenance and feature work.

For CPU affinity-specific sequencing, see:
- `Docs/10-affinity-prework-gate-plan.md`

## 1) Branch-specific launch setup still duplicated in `ServerInstance.start_server`
File: `app/classes/shared/server.py`

Issue:
- Spawn syscall is centralized via `_launch_server_process(...)`, but per-type launch preparation and error handling remain branch-heavy.

Impact:
- Feature additions can still drift if logic is added to only one server-type branch.

Recommendation:
- Continue consolidation by normalizing branch preparation and error semantics around the centralized launcher.

## 2) Custom command parser complexity (`Helpers.cmdparse`)
File: `app/classes/helpers/helpers.py`

Issue:
- custom parser handles quoting/escaping manually.

Impact:
- edge-case parsing differences vs platform shell expectations may be hard to reason about.

Recommendation:
- treat parser behavior as critical and add regression tests before changing command semantics.

## 3) Legacy import path appears stale
Files:
- `app/classes/shared/import3.py`
- `app/classes/shared/main_controller.py`

Issue:
- `Import3` references `controller.import_jar_server(...)`, but this method is not present in current `Controller` implementation.

Impact:
- legacy migration command may be broken or dead code.

Recommendation:
- confirm whether `import3` path is still supported; remove or repair explicitly.

## 4) Broad exception handling in lifecycle-critical code
Files:
- many, including `server.py`, `tasks.py`, helpers

Issue:
- broad `except:` patterns can suppress detail.

Impact:
- weak observability and harder incident diagnosis.

Recommendation:
- progressively replace with narrow exception handling and structured error logs.

Current status:
- launch path now has structured launch event logging and explicit failure reasons in `start_server`.
- broad exception usage still exists elsewhere and remains follow-up debt.

## 5) API security posture is permissive by default
Files:
- `base_handler.py`, `base_api_handler.py`

Issue:
- API XSRF disabled and CORS wildcard enabled.

Impact:
- requires strict token handling discipline and careful deployment hardening.

Recommendation:
- document this as explicit operational requirement; consider tightening posture where feasible.

## 6) Queue durability and observability limitations
File:
- `app/classes/shared/tasks.py`

Issue:
- command queue is in-memory and not durable.

Impact:
- lost queued work on process crash/restart.

Recommendation:
- if stronger delivery guarantees are needed, add persistent queue or idempotent replay mechanism.

## 7) Scheduler/model shape inconsistency risk
Files:
- `app/classes/models/management.py` (`Schedules`)
- `app/classes/shared/tasks.py`

Issue:
- schedule logic expects different types/values in some branches (e.g., reaction handling).

Impact:
- subtle runtime path issues for schedule creation/update edge cases.

Recommendation:
- normalize schedule model contracts and enforce one schema from API to scheduler.

## 8) High coupling between UI, API schema, and runtime behavior
Files:
- server config template and patch handlers

Issue:
- configuration field additions require coordinated changes in multiple layers.

Impact:
- easy to partially implement new fields and miss one layer.

Recommendation:
- use checklist-driven change process for any new server setting:
  - DB model + migration
  - API schema
  - UI form payload
  - runtime read/apply path
  - fallback/failed-server rendering paths

## 9) Thread-heavy runtime with limited explicit synchronization
Files:
- `ServerInstance`, `TasksManager`

Issue:
- shared mutable state updated from multiple threads.

Impact:
- potential race conditions around process state flags and lifecycle transitions.

Recommendation:
- when touching lifecycle code, reason explicitly about concurrent calls and idempotence.

## 10) Minor correctness/quality signals
Examples observed:
- typo-level issues (e.g., `logger.critcal` in one path).
- duplicated route declarations in some APIs.

Impact:
- small quality issues can indicate under-tested branches.

Recommendation:
- include lightweight static checks and branch-focused tests when modifying nearby code.

## 11) Process ownership depends on `execution_command` shape
Files:
- `app/classes/shared/server.py`
- `app/classes/shared/main_controller.py`

Issue:
- Crafty tracks only the PID returned by `Popen`.
- `execution_command` is operator-configurable and may launch wrappers/scripts rather than direct game process exec.

Impact:
- lifecycle controls and future host-resource controls (CPU affinity, cgroups) can target an unintended process model if wrappers fork/exit.

Recommendation:
- define supported command-shape expectations clearly.
- test process-tree behavior whenever launch semantics are changed.

Current status:
- PW2 scaffolding exists in `ServerInstance` for wrapper-shape inspection/policy hooks.
- validation of false-positive/false-negative behavior still depends on manual smoke execution against real commands.
