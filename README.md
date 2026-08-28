[![Crafty Logo](app/frontend/static/assets/images/logo_long.svg)](https://craftycontrol.com)
# Custom Crafty Controller 4.10.8
> Private custom build for local server management.

## Version Lineage
- **Current custom release:** `4.10.8` — up to date with official Crafty `v4.10.8`.
- **Historical upstream merge base:** `Crafty v4.10.3` (`0443b939`). This is the shared
  ancestry of the custom line, not the effective feature/fix level.
- **Upstream status:** up to date with `v4.10.8`; this custom fork uses equivalent custom
  implementations where an upstream refactor would conflict with local features.
- **Ported custom release scope:** Forge/NeoForge build selection and installer recovery; JVM
  memory validation; upload hardening; schedule Run Now and schedule copying; Hytale-aware player controls; player
  ordering/layout; telemetry; CPU affinity and memory caps.
- **Intentional divergence from upstream:** shared player-management and upload-route refactors,
  translations/CI churn, and architecture-only cleanup are not merged where they would overwrite
  or complicate custom behavior.
- **Future update rule:** compare the next official upstream release against this section and
  selectively port security fixes and compatible behavior; do not use the `4.10.3` merge base as
  an indicator that all intervening work is missing.

## What This Repo Is For
- Running Crafty locally on Windows/Linux for Minecraft server management.
- Tracking private customizations (UI, metrics, limits, permissions, telemetry).
- Custom launch controls:
  - per-server CPU affinity
  - hard RAM cap (`memory_limit_mib`)
- NBT editor support for `.dat` files with split permissions (`NBT_READ` / `NBT_WRITE`)
  and automatic backup on NBT save.
- CurseForge modpack updater in Update Center (API key + per-server profile).
- Forge/NeoForge creation uses the selected loader build and safe argument-vector launches on Linux.
  JVM heap fields and the process memory cap are all entered in MiB.
- Upload destinations and chunk staging paths are constrained to their approved roots.
- Player-management controls adapt to the server game type; Hytale bans use Hytale's own data and commands.
- Schedules can be manually queued from the Schedule page, subject to the existing Schedule permission.
- Profile image uploads accept only a small raster-image allowlist; update checks tolerate
  request failures without breaking the watcher.

## Player Management Enhancements
- Expanded page layout with dedicated sections for:
  - players
  - OP entries
  - whitelist entries
  - IP bans
  - banned players
- Added direct action controls for common moderation/admin tasks:
  - `OP` / `De-OP`
  - `Ban` / `Unban`
  - `IP Ban` / `Pardon IP`
  - `Kick`
  - `Whitelist add/remove`
- OP entries now support inline autosave edits:
  - level dropdown (`1-4`)
  - bypass limit toggle (styled switch)
- Added player head icons in player-management lists for faster scanning.

## Log Viewer Enhancements
- Added selectable log folder + source workflow (folder first, then source list).
- Source list now shows `Name | Last Modified | Path`.
- Added server-side full-log search with pagination controls.
- Added support for reading archived `.gz` logs directly.
- Detected log folders include standard logs plus:
  - `logs/`
  - `crash-reports/`
  - `kubejs/logs/`
- Per-user datetime format preference for log source timestamps:
  - `Browser / Auto`
  - `United Kingdom (DD/MM/YYYY 24h)`
  - `United States (MM/DD/YYYY 12h)`
  - `ISO 8601 (YYYY-MM-DD 24h)`

## Local Run (No Docker)
```powershell
cd <path-to-Crafty>
.venv\Scripts\python.exe main.py
```

## CurseForge API Scope (Implemented Baseline)
- Store global CurseForge API key (superuser).
- Configure per-server update profile:
  - project ID
  - optional pinned file ID
  - purge paths
  - overlay directory (relative to server root)
- Run guarded update flow from Update Center:
  - backup
  - purge configured paths
  - extract server zip
  - re-apply local overlay content
  - align Forge/NeoForge loader metadata when detected from the extracted pack
  - restart if the server was running before update
- If no server zip exists for a pack, update remains manual.

## Upstream Reference
- Upstream project: https://gitlab.com/crafty-controller/crafty-4

## License
This project remains under **GPLv3** per upstream licensing.  
Keep `LICENSE` and attribution intact when sharing or distributing builds/source.
