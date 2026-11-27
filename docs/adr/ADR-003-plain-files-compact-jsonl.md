# ADR-003: Plain files; compact-key JSONL for cards only

- **Status:** Proposed
- **Date:** 2026-11-27

## Context

Requirements: no database, user-readable data, low token cost, line-oriented append for sync safety.

## Decision

- Cards: JSONL with short keys (`k`, `s`, `d`, `r`, `txt`, …). One card per line. UTF-8, `\n` line endings on every OS.
- Registry: pretty-printed JSON (hub-generated, diff-friendly).
- Everything a human edits (`profile.yaml`, `roles/*.yaml`, `device.yaml`, `redact.yaml`): YAML with full-word keys, loaded with `ruamel.yaml` so comments survive round-trips.
- JSON Schema (draft 2020-12) is the single source of truth for all formats.

## Alternatives considered

SQLite (binary, sync-hostile); one Markdown file per card (thousands of files, slow on Drive and USB, awkward to validate); CSV (no nesting for results).

## Consequences

Compact keys cut card size by about 35 % and reduce LLM tokens when cards go to the compiler. They are less readable, so `cvprism show` pretty-prints with full names and [SCHEMA.md](../SCHEMA.md) documents every key.
