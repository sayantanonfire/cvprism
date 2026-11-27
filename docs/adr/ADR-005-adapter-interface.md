# ADR-005: Adapter interface and whole-file atomic replication

- **Status:** Proposed
- **Date:** 2026-11-27

## Context

Adding a transport should take one Python module. Transports differ: git has commits, synced folders have eventual consistency and conflict copies, USB has mount events.

## Decision

- Interface: `available()`, `push(outbox)`, `pull() -> Registry | None`, `status()`. Hub extensions: `pull_inboxes(dest)`, `publish(files)`.
- `push` copies whole changed files via write-to-tmp then atomic rename (or a commit for git). It never appends in place remotely.
- Adapters are discovered via Python entry points (`cvprism.adapters`), so third parties can ship adapters as separate packages.
- A shared conformance test suite (`tests/conformance/`) runs against every adapter.

## Alternatives considered

Remote append with byte offsets (fragile on synced folders, which may upload a stale whole file); rsync (not available on Windows by default); per-card files (file-count explosion).

## Consequences

Simple and idempotent. Re-copying a month file costs bandwidth proportional to its size (about 1 MB at most), which is negligible.
