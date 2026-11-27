# ADR-007: Hooks only enqueue; extraction via headless `claude -p` over a code-reduced digest

- **Status:** Proposed. This **amends** the kickoff spec, which had the SessionEnd hook *run* the extraction.
- **Date:** 2026-11-27

## Context

- A `SessionEnd` hook that runs a multi-second LLM call blocks or slows session shutdown, and may be killed.
- `claude -p` is itself a Claude Code session. Its own SessionEnd would trigger the hook again, causing recursion.
- Full transcripts are large (tokens = cost) and contain file contents and data (privacy).
- The user may use different Claude accounts per device. cvprism must not depend on account state.

## Decision

1. Hooks (Claude Code, git, watcher) append a small job record to `~/.cvprism/queue/` and exit. Target < 200 ms.
2. The background worker drains the queue. It sets `CVPRISM_EXTRACTING=1`, and the hook is a no-op when that variable is present.
3. A code-only **reducer** builds an allow-listed digest (see [SECURITY_PRIVACY.md](../SECURITY_PRIVACY.md)), capped at `max_input_tokens`.
4. The extractor calls `claude -p --output-format json` with all tools disabled, an optional `--model` (a cheap model by default), and a JSON Schema in the prompt. The output is validated, with one retry and then rejection.
5. An internal LLM-backend interface is kept, so a direct API or local-model backend can be added later without touching capture.

## Consequences

- Works with whatever account is logged in. No API key handling in cvprism.
- Capture has a delay of minutes, which is fine for CVs.
- If `claude` is unavailable, jobs wait (TTL 30 days) and manual `--raw` logging still works.
- Exact CLI flags (tool disabling, model selection, hook payload fields) are pinned and covered by tests at M2, because they can change between Claude Code releases.
