# ADR-009: Deterministic honesty gate for CV bullets

- **Status:** Proposed
- **Date:** 2026-11-27

## Context

"Never invent metrics" cannot be guaranteed by prompting alone. LLMs embellish, especially when tailoring to a job description.

## Decision

The compiler asks the LLM for bullets in a structured form `{text, cites: [card ids]}`, then applies a **code** gate:

1. `cites` is non-empty, and every ID exists in `cards.jsonl` and is not suppressed.
2. Every numeric token in `text` (digits, `%`, `x`/`×`, ranges, number words such as "two" to "twenty", "dozens", "hundreds") must match a value in a cited card's `r` (`val`, `base`, or a derived delta/ratio within ±1 % rounding) or a `profile.yaml` `facts` entry.
3. Skill names in the bullet should map to slugs in the cited cards or their registry parents. This is a soft check that warns rather than rejects.
4. A failing bullet gets one repair attempt with the failure reason. Then it is dropped and listed in `build/…/rejected.md`.

Every build also writes `evidence.md`, which maps each bullet to its cards.

## Consequences

Some legitimate phrasing is rejected (e.g. "two-phase approach" triggers on "two"). We accept these false positives and refine with an allow-list of non-metric number phrases. Users can always add a `facts` entry to assert a number themselves.
