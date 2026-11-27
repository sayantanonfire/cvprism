# ADR-011: Five-level depth ladder and novelty rules

- **Status:** Proposed
- **Date:** 2026-11-27

## Context

The novelty filter must tell "used an API" from "built an MCP server" in a way that is deterministic once the extractor has assigned a level.

## Decision

| d | Level | Typical evidence |
| --- | --- | --- |
| 1 | Used | Called an API, ran a tool, followed a tutorial |
| 2 | Applied | Used it to deliver part of a real project |
| 3 | Built | Built or integrated a component or system with it (e.g. an MCP server, a calibrated model) |
| 4 | Led / production | Deployed to production, optimised with measured results, led others, owned the decision |
| 5 | Authored / taught | Published, taught, contributed upstream, created a method others use |

Novelty rule for a candidate card `c` against registry `R`:

```text
emit card if  any(slug not in R for slug in c.s)           # new skill
          or  any(c.d > R[slug].max_d for slug in c.s)     # depth up
          or  (c.r and fp(c.r) not in R[slug].rh)           # new measurable result
          or  c.k == "work"                                 # papers, talks, field work: always
else          counters[slug].n += 1; counters[slug].last = now
```

The hub re-applies the rule at merge against the authoritative registry. A non-novel card that arrives late is kept (it is valid evidence) but flagged `needs_review`.

## Consequences

The extractor's rubric must state the ladder explicitly, with examples per level. Depth is a claim: the honesty gate does not verify it, and review mode lets users correct it.
