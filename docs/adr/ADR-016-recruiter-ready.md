# ADR-016: Recruiter-ready output through code-enforced writing rules and an ATS read-back

- **Status:** Accepted
- **Date:** 2026-11-28

## Context

An honest CV still has to win the first 10 seconds with a recruiter and survive an ATS parser. The owner asked for CVs that never repeat themselves, never sound boring, and are ready for applicant tracking systems. As with the honesty gate (ADR-009), these are rules we can check in code instead of hoping a prompt follows them.

## Decision

**Writing quality (`compile/quality.py`)**

- **Near-duplicate lines** (same skills and ≥ 60 % word overlap) are merged into the stronger line: higher proof level, then score. Their citations are combined.
- **Repeated opening verbs:** the second and later uses of a verb are swapped for a vetted synonym from the same meaning group (Built → Developed → Engineered …). This is applied only when the bullet starts with that verb, so meaning is preserved and the honesty gate still passes.
- **Weak openers** ("Responsible for", "Worked on", "Helped"), **buzzwords** ("passionate", "results-driven", "synergy") and **over-long lines** (> 35 words) are reported in `quality.md`. With Claude drafting enabled, the prompt forbids them and asks for challenge → action → result lines.

**ATS read-back (`compile/ats.py`)**

- After rendering, cvprism extracts the text of `cv.pdf` (pypdf) and `cv.docx` (python-docx) the way a parser would, then checks:
  - the name and email appear near the top
  - standard section headings are present
  - every bullet's text survives extraction
  - proof links are visible as text, not hidden behind icons
  - the file is under 2 MB
- With `--jd`, it scores keyword coverage. It reports JD skills that have evidence but didn't make it into the CV (an opportunity) separately from real gaps (no evidence, never added).
- Results go to `ats.md` and a one-line summary in the build log.

## Alternatives considered

- Asking the LLM to "avoid repetition": not enforceable, and unavailable in `--no-llm` builds.
- Paraphrasing whole bullets in code: risks changing meaning, so only the first verb is swapped.
- Third-party ATS scoring APIs: they would send the CV off-device, so they're rejected.

## Consequences

Two new artifacts per build: `quality.md` and `ats.md`. pypdf joins the `[pdf]` extra. ATS checks are heuristics; they catch real breakages (lost text, hidden contacts, odd headings) but no tool can guarantee every ATS vendor's behaviour.
