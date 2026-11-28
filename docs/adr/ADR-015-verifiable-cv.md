# ADR-015: Verifiable CV through project-level visibility and computed proof levels

- **Status:** Accepted
- **Date:** 2026-11-28
- **Spec:** [2026-11-28 Verifiable CV design](../superpowers/specs/2026-11-28-verifiable-cv-design.md)

## Context

In 2026 recruiters report they cannot trust CVs, and detection of AI-polished CVs performs no better than chance. cvprism's honesty gate is invisible to a reader. We need checkable proof on the CV itself, without exposing private work and without demoting skills learned in closed-source projects.

## Decision

1. **Visibility is a property of the project** (`public | private | local`), stored only on the hub. Cards stay immutable and links are resolved at build time.
2. **Proof levels are computed** from evidence (`public`, `confirmed`, `captured`, `self-reported`), never entered by the user.
3. **Private work is first-class.** It always appears; only the link is replaced by *(private repository)*, or by nothing for local work.
4. **Verification is self-hosted:** an Evidence appendix in every CV, plus an optional static page on the user's own GitHub Pages with a SHA-256 fingerprint of the PDF. There is no central server (consistent with ADR-001/ADR-014).
5. **Links appear as visible URL text, not icons**, to keep the CV ATS-safe.

## Alternatives considered

- Links stored inside cards: rejected, because visibility changes over time and cards are immutable.
- Automatic linking of any public-host remote: rejected, because it risks advertising repos the user didn't intend to.
- A central verify service: deferred. It needs servers and accounts, and could come later as an optional layer.
- Per-bullet proof symbols: rejected, because they can confuse ATS parsers. Levels live in the appendix instead.

## Consequences

- A truthful candidate's CV becomes distinguishable: proof is one click away.
- A self-hosted fingerprint proves integrity, not truth. The UI says this explicitly.
- Users must mark projects public once. `cvprism project set` makes that a single command.
