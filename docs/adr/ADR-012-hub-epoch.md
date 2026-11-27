# ADR-012: Hub identity and promotion via epochs

- **Status:** Proposed
- **Date:** 2026-11-27

## Context

"A device can be promoted to hub later." Without coordination, two hubs could publish competing registries (split brain), especially over slow transports like USB.

## Decision

- `hub.json = {v, hub_device_id, epoch}`, written only by the hub.
- `cvprism hub promote` reads the highest `hub.json` across all reachable transports, writes `epoch+1` with its own ID, then runs `hub rebuild` from all inboxes.
- Every hub checks `hub.json` before each merge. If it sees a higher epoch (or an equal epoch with a lexicographically greater device ID), it demotes itself to spoke.
- Registries carry `(epoch, rev)`. Spokes accept only strictly newer ones.

## Consequences

There is no consensus protocol, and none is needed. The worst case is a temporary second registry. That is harmless, because registries only steer novelty and the hub re-checks at merge.
