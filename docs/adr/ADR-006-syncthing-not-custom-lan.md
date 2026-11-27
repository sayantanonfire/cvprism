# ADR-006: Syncthing instead of a custom LAN server

- **Status:** Proposed
- **Date:** 2026-11-27

## Context

The user wants machines on the same LAN to sync with no cloud. A homemade server must handle discovery, NAT and firewalls, TLS, auth, resumable transfer and Windows service quirks. That is months of edge cases outside our core value.

## Decision

Ship a `syncthing` adapter that treats a Syncthing-shared folder like a plain folder. cvprism generates the folder configuration and pairing instructions, and checks Syncthing's local REST API for health. A native `cvprism hub serve` stays on the post-v1 roadmap.

## Consequences

The user installs Syncthing (open source, cross-platform). Both machines must be online at the same time for transfer, and the outbox covers the gaps. Transport security and resumption come from a mature project.
