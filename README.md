[![Crafty Logo](app/frontend/static/assets/images/logo_long.svg)](https://craftycontrol.com)
# Custom Crafty Controller 4.10.4
> Private custom build for local server management.

## Version Lineage
- **Current local/custom version:** `4.10.4`
- **Upstream base used for this custom line:** `Crafty v4.10.3`
- This repo is intentionally customized beyond upstream for private use.

## What This Repo Is For
- Running Crafty locally on Windows/Linux for Minecraft server management.
- Tracking private customizations (UI, metrics, limits, permissions, telemetry).
- Custom launch controls:
  - per-server CPU affinity
  - hard RAM cap (`memory_limit_mib`)
- NBT editor support for `.dat` files with split permissions (`NBT_READ` / `NBT_WRITE`)
  and automatic backup on NBT save.
- Optional CurseForge API integration work for modpack update workflows.

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

## CurseForge API Scope (Planned/Partial)
- Query selected modpack metadata and versions.
- Download server packages when available.
- Run a guarded update flow:
  - backup
  - purge configured paths
  - re-apply local overlay content (`mods/`, `config/`, `kubejs/`, etc.)
- If a pack has no server package, update remains manual.

## Upstream Reference
- Upstream project: https://gitlab.com/crafty-controller/crafty-4

## License
This project remains under **GPLv3** per upstream licensing.  
Keep `LICENSE` and attribution intact when sharing or distributing builds/source.
