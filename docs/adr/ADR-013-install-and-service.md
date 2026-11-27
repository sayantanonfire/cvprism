# ADR-013: Venv in the user data dir; OS-native login services

- **Status:** Proposed
- **Date:** 2026-11-27

## Context

Install must work from a git clone or a USB stick, and capture must continue after the stick is removed.

## Decision

- `start.sh` / `start.bat` locate Python ≥ 3.10, create a venv in the platform data dir (`%LOCALAPPDATA%\cvprism`, `~/Library/Application Support/cvprism`, `~/.local/share/cvprism`) and `pip install` cvprism **from the stick or clone path**. A bundled wheelhouse on the USB stick allows offline install. After install, nothing references the stick.
- The background service (`cvprism agent`) is registered per OS: a Windows Task Scheduler "at logon" task (no admin rights), a macOS `launchd` LaunchAgent, or a Linux `systemd --user` unit with an XDG autostart fallback.
- Hooks point at the venv's absolute `cvprism` executable path.
- `cvprism uninstall` removes services and hooks, restores prior git and Claude Code settings, and keeps data unless `--purge-data` is given.

## Alternatives considered

pipx (good, but not guaranteed to be installed; supported as an alternative path), a PyInstaller single binary (large, and antivirus false positives on Windows), Docker (cannot easily hook the host's Claude Code or git).

## Consequences

No admin rights needed on any OS. Python must already be installed. The start script prints per-OS install instructions if it is missing.
