# Crafty Internal Documentation

This `/Docs` directory is intended for engineers who need to understand this codebase before changing behavior.

Scope:
- runtime architecture
- startup/bootstrap sequence
- server lifecycle and process management
- background tasks, queueing, and scheduling
- API/UI/config flow
- data model and persistence
- security/performance/operational risks
- known fragility and technical debt
- per-server CPU affinity implementation and operations

## Document Map

- `00-runtime-flow-diagram.md`
  - Canonical one-page request-to-process and config-to-runtime flow diagram.
- `01-architecture-overview.md`
  - High-level system architecture and component boundaries.
- `02-startup-and-runtime-bootstrap.md`
  - Process startup, migration flow, and long-running threads/services.
- `03-server-lifecycle-and-process-control.md`
  - How server processes are launched, supervised, restarted, updated, backed up, restored, and stopped.
- `04-background-jobs-queue-and-scheduling.md`
  - APScheduler usage, command queue behavior, and schedule execution paths.
- `05-web-api-ui-config-flow.md`
  - Tornado routing, API patterns, auth flow, and config propagation from UI/API to runtime.
- `06-data-model-persistence-and-migrations.md`
  - Main DB models, per-server stats DB, migration mechanics, and storage behavior.
- `07-security-performance-and-operational-risks.md`
  - Security-sensitive paths, performance hotspots, and operator-impacting risks.
- `08-fragility-and-technical-debt.md`
  - Known weak areas and practical maintenance guidance.
- `09-safe-modification-playbook.md`
  - Checklist-driven guidance for making changes safely across lifecycle-critical paths.
- `10-affinity-prework-gate-plan.md`
  - Pre-implementation hardening phases that must complete before CPU affinity feature work.
- `11-pw0-baseline-and-smoke-matrix.md`
  - PW0 baseline launch behavior and repeatable manual smoke matrix for lifecycle paths.
- `affinity-plan-per-server-cpu-affinity.md`
  - Detailed, phased plan and implementation status for per-server CPU affinity support.
- `12-cpu-affinity-operator-runbook.md`
  - Operator rollout, verification, troubleshooting, and rollback guide for CPU affinity.
- `13-absolute-memory-limit-plan.md`
  - Phased plan for Linux absolute per-server RAM limits, UI/API changes, lifecycle enforcement, and memory-reporting normalization.
- `14-curseforge-modpack-update-spec.md`
  - End-to-end feature specification for CurseForge-backed modpack updates (profile config, safe apply pipeline, purge/overlay behavior, and loader alignment).

## Notes on Accuracy and Uncertainty
- Function names and file paths are referenced directly from the source at documentation time.
- Line numbers are intentionally not treated as stable; use symbol/function names when searching.
- Where behavior is unclear from static inspection, uncertainty is explicitly called out.
