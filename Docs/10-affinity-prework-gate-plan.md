# 10. Affinity Pre-Work Gate Plan

## Purpose
This document defines the pre-work that must be completed before per-server CPU affinity implementation begins.

It focuses on reducing fragility in the exact areas that CPU affinity will touch:
- process launch path
- PID ownership assumptions
- command parsing behavior
- launch-time error and observability model

This is a gate plan, not feature implementation.

## Why This Exists
`ServerInstance.start_server` has thread-heavy lifecycle behavior and still branch-heavy launch setup.
Adding affinity directly without hardening these launch seams increases risk of:
- partial feature coverage across lifecycle paths
- process ownership mistakes
- hard-to-debug operational failures

Relevant debt items are documented in:
- `Docs/08-fragility-and-technical-debt.md`

## Scope
In scope pre-work:
- launch path consolidation in `app/classes/shared/server.py`
- command parser regression tests for `Helpers.cmdparse` in `app/classes/helpers/helpers.py`
- explicit launch error semantics and logs
- wrapper command-shape policy hooks needed for affinity safety

Out of scope pre-work:
- global queue durability redesign
- full scheduler model cleanup
- broad auth/CORS policy redesign
- legacy `Import3` cleanup

Explicit anti-goal:
- do not attempt to support every possible wrapper behavior.
- unsupported wrapper patterns must be rejected by policy, not accommodated with ad-hoc compatibility logic.

## Phase Plan

## PW0: Baseline and Safety Net
Objective:
- establish baseline behavior before changing launch internals

Work:
- capture current launch behavior for representative launch branches (`minecraft-java` or `hytale`, `minecraft-bedrock`, `steam_cmd`) from `ServerInstance.start_server`
- define a repeatable manual smoke matrix for:
  - start
  - restart
  - crash recovery restart
  - scheduled start/restart
  - update restart
  - backup-triggered restart

Files:
- `app/classes/shared/server.py`
- `app/classes/shared/tasks.py`
- `Docs/03-server-lifecycle-and-process-control.md`

Exit criteria:
- baseline matrix documented and reproducible
- known expected behavior per server type written down

PW0 evidence artifact:
- `Docs/11-pw0-baseline-and-smoke-matrix.md`

PW0 status:
- completed (documentation baseline captured)

## PW1: Launch Path Consolidation (No Behavior Change Intended)
Objective:
- remove duplicated `Popen` call paths by introducing one internal launcher helper

Work:
- refactor `ServerInstance.start_server` to centralize spawn logic into a single helper
- preserve existing env/cwd/stdin/stdout behavior for each server type
- keep launch semantics equivalent (no affinity logic yet)

Files:
- `app/classes/shared/server.py`

Exit criteria:
- all baseline flows from PW0 pass
- all spawn paths route through one helper
- no regressions in stop/kill/crash detection behavior

PW1 evidence artifact:
- `app/classes/shared/server.py` (`_launch_server_process` and `start_server` callsites)

PW1 status:
- implementation complete (launcher helper introduced)
- validated for default launch branch (`minecraft-java`) based on operator lifecycle smoke
- non-default branch runtime smoke (`minecraft-bedrock`, `steam_cmd`) deferred and tracked as accepted implementation risk for this fork

## PW2: PID Ownership and Wrapper Policy Scaffolding
Objective:
- make process ownership expectations explicit before resource controls are introduced

Work:
- define supported command shapes for managed launch:
  - direct executable
  - wrapper using `exec`
- define unsupported command shape:
  - fork/daemonize-and-exit parent
- add startup command-shape check scaffolding needed for affinity mode:
  - startup grace-window config (default `5s`, tunable)
  - parent/child process inspection hooks

Files:
- `app/classes/shared/server.py`
- `Docs/03-server-lifecycle-and-process-control.md`
- `Docs/affinity-plan-per-server-cpu-affinity.md`

Exit criteria:
- unsupported wrapper behavior can be detected deterministically by policy hook
- no false-positive behavior in baseline commands used by this deployment

PW2 evidence artifact:
- `app/classes/shared/server.py`:
  - `_get_wrapper_policy_mode`
  - `_get_wrapper_startup_grace_seconds`
  - `_snapshot_process_children`
  - `_inspect_wrapper_process_shape`
  - `_apply_wrapper_policy`
  - `start_server` wrapper-policy hook callsite

PW2 status:
- implementation complete (policy scaffolding and process-tree inspection hooks added)
- validated for non-regression on default policy mode (`disabled`) during operator lifecycle smoke
- explicit `audit`/`enforce` runtime validation remains pending and is tracked for post-implementation hardening

Link to affinity plan:
- PW2 provides the enforcement mechanism used by:
  - `Docs/affinity-plan-per-server-cpu-affinity.md` Section `5.2` (process model constraints)
  - `Docs/affinity-plan-per-server-cpu-affinity.md` Section `8` (deterministic failure semantics)
  - `Docs/affinity-plan-per-server-cpu-affinity.md` Section `13` (PID/process-tree correctness validation)

## PW3: Command Parsing Regression Guardrails
Objective:
- lock down command tokenization behavior so launch refactors do not silently change argv shape

Work:
- add tests for `Helpers.cmdparse` covering:
  - quoted paths
  - escaped quotes/backslashes
  - mixed arguments used in existing server commands
- include representative commands from create/import paths in:
  - `app/classes/shared/main_controller.py`

Files:
- `app/classes/helpers/helpers.py`
- test suite files for helper parsing

Exit criteria:
- parser test suite passes and covers current production command patterns
- launch refactor does not alter tokenization outcomes for validated fixtures

PW3 evidence artifact:
- `tests/classes/helpers/test_cmdparse.py`
- local execution evidence (Windows 11, Python 3.11 venv):
  - command: `python -m pytest tests\classes\helpers\test_cmdparse.py -q`
  - result: `8 passed in 1.54s`
- local agent execution evidence:
  - command: `.venv\Scripts\python.exe -m pytest tests\classes\helpers\test_cmdparse.py -q`
  - result: `8 passed in 0.43s`

PW3 status:
- validated
- regression fixtures added for create/import-style commands
- local execution completed and passing in operator-provided environment

## PW4: Launch Error Model and Observability
Objective:
- make launch failures deterministic and operator-visible before affinity adds new failure modes

Work:
- define structured launch failure reasons (validation failure, unsupported command shape, spawn failure, dependency unavailable)
- standardize logs for launch attempts and outcomes
- ensure websocket/API-visible error propagation remains clear
- add mandatory debug hooks that can emit:
  - final launch argv used
  - PID returned from spawn
  - detected process tree details when wrapper-policy checks trigger

Files:
- `app/classes/shared/server.py`
- `app/classes/web/routes/api/servers/server/action.py`
- `app/classes/web/routes/api/servers/server/index.py`

Exit criteria:
- operator can tell why launch failed without reading stack traces
- no silent fallback behavior in safety-sensitive launch checks
- debug hooks are sufficient to reconstruct launch ownership decisions during incident review

PW4 evidence artifact:
- `app/classes/shared/server.py`:
  - `_build_launch_event_payload`
  - `_log_launch_event`
  - `_notify_start_error`
  - `start_server` structured launch event and failure-reason logging
  - wrapper-policy trigger logs include detected process tree details

PW4 status:
- implementation complete (structured launch observability and deterministic failure reason logging added)
- validated for default launch branch (`minecraft-java`) from operator-reported lifecycle smoke:
  - start from panel: pass
  - stop from panel: pass
  - restart from panel: pass
  - crash detection + auto-restart after forced process close: pass
  - scheduled start: pass
  - scheduled restart: pass
- additional branch/runtime-mode validation (`minecraft-bedrock`, `steam_cmd`, `hytale`) remains deferred by operator choice and is tracked as accepted risk

## Gate to Start Affinity Feature Work
No partial rollout rule:
- affinity must not be enabled on any server until PW1 through PW4 are complete and validated.

All of the following must be true:
1. PW0 through PW4 exit criteria are met.
2. Real-host spike confirms chosen affinity primitive against production-style commands.
3. Documentation is updated to reflect final pre-work behavior.

Only then start feature phases in:
- `Docs/affinity-plan-per-server-cpu-affinity.md`

## Risk Notes
- PW1 and PW2 can expose latent wrapper/process-model assumptions already present in this project.
- If baseline commands include wrapper/fork patterns, policy decisions may require command cleanup before affinity can be safely enabled.
- Do not broaden scope into unrelated debt cleanup during these phases.
- This fork is proceeding with affinity implementation across all server modes while only `minecraft-java` lifecycle smoke is currently validated.
- Untested runtime-mode risk for `minecraft-bedrock`, `steam_cmd`, and `hytale` is explicitly accepted for this implementation phase.

## Gate Decision (Current)
- decision: GO for affinity implementation work.
- rationale:
  - pre-work code changes are in place
  - operator lifecycle smoke passed for the default launch branch (`minecraft-java`)
  - remaining non-default branch validation is explicitly accepted as deferred risk

## Definition of Done for Pre-Work
- launch path is centralized
- parser behavior is regression-tested
- PID ownership policy is explicit and testable
- launch failures are deterministic and observable
- docs reflect actual post-pre-work behavior
