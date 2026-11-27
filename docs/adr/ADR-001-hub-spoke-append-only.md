# ADR-001: Hub-and-spoke topology with append-only per-device inboxes

- **Status:** Proposed
- **Date:** 2026-11-27

## Context

Users work on several machines, possibly under different Claude accounts, and want one place to build CVs. The transports we must support (git, consumer synced folders, USB sticks, Syncthing) have very different consistency semantics. Synced folders in particular produce conflict copies and partial uploads.

## Decision

- One hub per vault. All other devices are spokes. Spokes never talk to each other.
- Each device writes only to `inbox/<device-id>/YYYY-MM.jsonl`, append-only, one complete line per record.
- The hub is the single writer of `cards.jsonl` and `registry.json`.
- Merge is a set union by content-hash ID ([ADR-002](ADR-002-content-hash-ids.md)). The data model is a grow-only set CRDT.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Single shared `cards.jsonl` written by all devices | Concurrent writes conflict on every transport, git included |
| Peer-to-peer mesh (every device merges) | N² sync paths, harder reasoning. CVs are built on one machine anyway |
| SQLite per device and a replication tool | Binary files sync badly over Drive and USB, and break the "plain files" requirement |

## Consequences

- Conflict-free on every transport by construction. Correctness does not depend on clocks or delivery order.
- Files grow forever. At around 2 KB/card and a few cards a day this is about 1 MB/year, which is acceptable.
- Deletion needs explicit mechanisms (`suppress`, `purge`; see [SECURITY_PRIVACY.md](../SECURITY_PRIVACY.md)).
- The hub is a soft single point of failure for compiling, mitigated by [ADR-012](ADR-012-hub-epoch.md) (promotion and rebuild from inboxes).
