# ADR-014: What v1.0 deliberately leaves out

- **Status:** Accepted
- **Date:** 2026-11-27

## Context

The M6 roadmap listed Syncthing CI against real instances and optional `age` encryption of transport files. Both are useful but neither blocks a correct, safe v1.

## Decision

- **Syncthing CI with real daemons**: deferred. The Syncthing adapter is a plain-folder adapter. It passes the same conformance suite as gdrive/local, and transport correctness belongs to Syncthing itself. Pairing two daemons in CI adds flaky infrastructure for little extra assurance.
- **`age` encryption of inbox files**: deferred to v1.1. Cards contain no secrets by construction (reducer allow-list, redactor, schema length caps). Encryption needs key distribution to every spoke, which deserves its own design.
- **PyPI publishing**: automated in `release.yml` via trusted publishing. The owner enables it once on pypi.org.
- **Native `cvprism hub serve`**: post-v1, as ADR-006 already decided.

## Consequences

v1 users who need encryption at rest on a shared transport should use an encrypted private git repo or their cloud provider's encryption. SECURITY_PRIVACY.md documents this exposure.
