# Changelog

## 1.0.0 (2026-11-27)

First public release.

### Capture
- `cvprism log` with Claude-normalised, market-facing wording, or `--raw` offline. Metrics you did not state are never kept.
- Automatic capture from Claude Code sessions (SessionEnd hook), git commits (chaining global hook dispatcher) and opted-in project folders (dependency and tool names only).
- Code-only reducers and a redactor (secret scanners, deny-terms, path/URL/email scrubbing, plugins) before anything reaches an LLM.
- Novelty filter: a new card only for a new skill, a higher depth, a new measurable result, or non-code work.
- `cvprism import-linkedin`, `import-cv`, `import-orcid` to bootstrap from what you already have.

### Sync
- Hub-and-spoke, append-only per-device inboxes, content-hash card IDs: conflict-free over every transport.
- Adapters: private git repo, synced folders (Google Drive, OneDrive, Dropbox), USB drop-box, Syncthing, local folder. Several at once; offline outbox.
- Hub merge with quarantine, `suppress`, `purge`, epochs and `hub promote`; registry flows back to spokes.

### Compile
- `cvprism build --role <role>` and `--jd <file|url>` to PDF (RenderCV/Typst, fitted to the page limit), DOCX and Markdown.
- A deterministic honesty gate: every bullet cites cards, and every number must trace to evidence. `evidence.md`, `rejected.md`, `gaps.md`.
- Five starter roles with `extends` inheritance; market-phrase intel from postings you save.

### Usability
- `start.sh` / `start.bat` from a clone or USB stick; terminal or browser (`cvprism init --web`) setup.
- `cvprism install` / `uninstall` (fully reversible), background agent at login on Windows, macOS and Linux.
- `cvprism demo` builds sample CVs offline in seconds.
