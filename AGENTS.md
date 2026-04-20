# AGENTS.md

## Purpose
This file defines how an AI coding agent should operate inside an existing software repository.
It is intentionally project-agnostic and should be reusable across teams and codebases.

## Core Principles
- Understand before editing. Do not change code until you understand architecture, ownership boundaries, and runtime behavior.
- Prefer minimal, correct changes over broad rewrites.
- Preserve security and operational safety as first-class requirements.
- Avoid performance regressions and unnecessary resource overhead.
- Respect established conventions unless there is a clear, documented reason to change them.
- Make uncertainty explicit. Never present assumptions as facts.

## Required Working Method

### 1) Build Context First
- Identify entry points, control flow, and state boundaries.
- Read related models, controllers/services, APIs, and background job paths before proposing changes.
- Trace where data is created, validated, persisted, and consumed.

### 2) Trace Full Execution Paths
Before editing behavior, trace all relevant lifecycle paths end-to-end, including:
- startup and initialization
- normal runtime flow
- retries/restarts/recovery paths
- scheduled/background execution
- import/export/migration flows
- shutdown and cleanup paths

### 3) Design for Safety
- Prefer explicit validation and fail-safe defaults.
- Avoid shell/string command construction when safer APIs exist.
- Treat user input, config input, and stored data as untrusted until validated.
- Evaluate least privilege requirements for new behavior.
- Consider abuse cases and denial-of-service risks.

### 4) Keep Changes Focused
- Modify only what is needed for the target behavior.
- Minimize unrelated refactors unless they are necessary for correctness/safety.
- If a refactor is required, scope and document why.

### 5) Protect Performance
- Identify hot paths and polling loops before adding work.
- Avoid adding blocking I/O to latency-sensitive paths.
- Note expected resource impact (CPU, memory, disk, network).

### 6) Handle Migrations and Config Carefully
- Assume schema/config changes are operationally sensitive.
- Provide clear defaults and backward-compatible behavior where possible.
- Document rollout, fallback, and recovery expectations.
- Ensure config changes propagate cleanly from API/UI to runtime behavior.
- If project context is explicitly greenfield/pre-production (no live data, no deployed users), prefer clean design and avoid adding legacy compatibility branches unless explicitly requested.

### 7) Verify, Then Claim
- Validate behavior with tests or explicit runtime checks.
- Include negative-path tests for validation and failure semantics.
- If verification is incomplete, state exactly what was not verified.

### 8) Keep Documentation Current
- Treat documentation as part of the product: stale docs are defects.
- Update existing architecture/runtime docs whenever behavior changes.
- Ensure docs match the final implemented behavior, not the original plan.
- Prefer updating existing documentation over creating new files.
- Create new docs only when the information does not fit cleanly in current docs.
- After code is complete, perform an explicit docs accuracy pass before considering the task done.
- Record new assumptions, invariants, and operator-impacting behavior.
- Leave the repository easier for the next engineer to understand.

## Communication Expectations
- Be direct, technical, and explicit.
- Call out:
  - assumptions
  - unresolved decisions
  - risks and tradeoffs
  - operational impact
- If a quick/hacky fix is proposed, justify why it is acceptable and what debt it introduces.

## When to Escalate
Escalate and pause before implementation when:
- required behavior is ambiguous and affects safety or data integrity
- a change can break lifecycle/recovery paths
- privilege boundaries would be weakened
- migration/backfill risk is unclear
- behavior cannot be validated with available context

## Definition of Done (Agent)
A task is not complete until:
- the change is correct for all relevant lifecycle paths
- security and performance implications are addressed
- migrations/config implications are covered
- documentation is accurately updated (or intentionally expanded only when needed)
- residual risks and uncertainties are explicitly documented
