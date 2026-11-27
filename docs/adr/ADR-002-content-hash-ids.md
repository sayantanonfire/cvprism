# ADR-002: Card IDs hash canonical fields, not free text

- **Status:** Proposed. This **amends** the kickoff spec, which said "sha256 of normalised fields, excluding device and timestamp".
- **Date:** 2026-11-27

## Context

The kickoff spec wants the same achievement captured twice anywhere to dedup automatically. But the two captures come from an LLM, often from different sources (a Claude session and a git commit). Their wording (`txt`, `meth`) will almost never match byte-for-byte. A hash that includes free text would dedup almost nothing.

## Decision

`id = "c_" + sha256(canonical_json({k, sorted(s), d, normalised r, ctx}))[:16]`

- Only **structured** fields are hashed: kind, skill slugs (after registry alias normalisation), depth, normalised result, and project alias.
- Free text, tools, domains, confidence, device, timestamp and source are excluded.
- The ID is truncated to 64 bits. The birthday bound for collisions is about 4×10⁹ cards, far beyond a personal vault. The hub recomputes IDs on merge.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Hash all fields except device/time | Near-zero dedup across sources, as above |
| Embedding-similarity dedup | Non-deterministic, needs a model on every device. May be added later as an *advisory* hub-side pass |
| UUIDs plus a hub-side LLM dedup | Costs tokens on every merge, non-reproducible |

## Consequences

- Dedup quality depends on **slug normalisation**. The registry alias table is therefore on the critical path, and the extractor must choose slugs from the registry when one fits (it gets the top-N candidate slugs in its prompt).
- Two genuinely different achievements with identical structure (e.g. two different MCP servers at depth 3 with no `ctx`) collapse into one card. That is acceptable: for novelty they are the same evidence, and `ctx` separates them when it matters.
- `k` must be a pure function of card content (`work` > `result` > `skill`). An earlier draft had a `depth` kind, but whether something is a level-up depends on what the capturing device already knows. That would give the same achievement different IDs on different devices, so the novelty reason now lives in the unhashed `why` field.
- Changing the canonical form is a breaking change and needs `v: 2` plus a migration.
