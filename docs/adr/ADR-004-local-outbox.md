# ADR-004: Local outbox is the source of truth; spokes hold no vault

- **Status:** Proposed. This **amends** the kickoff layout, which implied every device writes into a `vault/inbox/<device-id>/` folder.
- **Date:** 2026-11-27

## Context

If a spoke's only copy of a card lives inside a transport folder (a Drive folder, a git clone, a USB stick), then removing the stick or a Drive "free up space" action can lose it. A spoke that holds a full vault also means a lost laptop exposes the whole career history and profile.

## Decision

- Every device writes cards first to `~/.cvprism/outbox/<device-id>/YYYY-MM.jsonl` on local disk.
- Adapters *replicate* outbox files to `inbox/<device-id>/` at each transport, tracking a `(size, sha256)` cursor per adapter and file.
- Spokes receive only `registry.json`, `hub.json` and `vault.json`. Only the hub holds `cards.jsonl` and `profile.yaml`.
- The hub's own captures use the `local` adapter into its own vault, so the code path is the same.

## Consequences

- The offline outbox comes for free: it is the outbox.
- Multiple adapters are independent. Each has its own cursor.
- Building a CV away from the hub is not possible in v1 (Open question 8 in [ARCHITECTURE.md](../ARCHITECTURE.md)).
