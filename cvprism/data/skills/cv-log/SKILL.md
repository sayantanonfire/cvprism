---
name: cv-log
description: Record a CV-worthy achievement with cvprism (a paper, talk, field work, award, a skill learned, or a measurable result). Use when the user says /cv-log, "log this for my CV", or "add this to my CV evidence".
---

# cv-log (cvprism)

Record one achievement as a cvprism evidence card.

1. Ask, if not already clear from the conversation:
   - **What** was done, in one sentence (methodology and skills, not data).
   - **Number**: a measurable result *only if the user states one*. Never estimate or invent a metric.
   - **Project alias** (optional, short, no client names).
2. Run `cvprism log` with a single line. Examples:
   - `cvprism log "Calibrated Manning's n for a 2D HEC-RAS model using Bayesian inference"`
   - `cvprism log --raw "Presented flood copilot at EGU 2026" --skill science-communication --depth 5 --work`
   - `cvprism log "Cut tile rendering time" --result "render time:-60:%"` (only if the user gave 60%)
3. Show the user the command's output (new card, or "already known").

Rules:
- Never paste file contents, code, data, credentials, client or colleague names into the log line.
- If `cvprism` is not on PATH, tell the user to run the cvprism `start` script first.
