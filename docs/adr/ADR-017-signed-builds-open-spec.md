# ADR-017: Signed builds with existing SSH keys, and an open manifest specification

- **Status:** Accepted
- **Date:** 2026-11-28

## Context

The verify page (ADR-015) proves a CV file wasn't altered, but anyone could publish a page under any name. Recruiters also need a way to check CVs that doesn't depend on cvprism existing, if the format is ever to become an industry habit.

## Decision

1. **Sign with the key people already have.** `cvprism build --sign` signs `manifest.json` with `ssh-keygen -Y sign` (namespace `cvprism-cv`), using the SSH key the author uses for GitHub. GitHub publishes every user's public keys at `github.com/<user>.keys`, so `cvprism verify --github <user>` (or plain OpenSSH) checks who produced the CV. There are no new key types, no accounts, and no servers.
2. **Publish the format as an open spec** (`docs/spec/evidence-linked-cv-v1.md`, Apache-2.0) with a JSON Schema, so other builders and ATS vendors can produce and consume it.
3. **Publish the exact bytes.** The verify page copies the build's `manifest.json` byte-for-byte, so signatures remain valid.

## Alternatives considered

- **W3C Verifiable Credentials / Open Badges 3.0:** the right long-term home for third-party attestations, but heavy for a self-asserted CV today (DID methods, JSON-LD). The spec leaves room for a future `confirmed` level backed by VCs.
- **GPG signatures:** fewer people have GPG keys than SSH keys on GitHub.
- **A central signing service:** needs servers and accounts, which we rejected in ADR-014.

## Consequences

Signing requires OpenSSH ≥ 8.2 (Git for Windows and current macOS/Linux include it). A signature binds the manifest to a key holder; it does not make claims true. The spec and the verify page both say so.
