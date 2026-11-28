# Verifiable CV: evidence links and proof levels

- **Date:** 2026-11-28
- **Status:** Approved by owner, in implementation
- **Decision record:** [ADR-015](../../adr/ADR-015-verifiable-cv.md)

## Problem

Recruiters no longer trust CVs: AI polish made every CV look equally good, so polish stopped being a signal. cvprism already refuses unsupported claims, but a recruiter cannot see that. A cvprism CV must make its honesty *visible and checkable*, without exposing private or client work and without ever dropping skills learned in closed-source projects.

## Decisions (from brainstorming)

1. **Link sources:** automatic, opt-in per project; manual links for anything else.
2. **Verification:** an Evidence appendix in every CV, plus an optional static verify page on a GitHub Pages repo the user owns.
3. **In the body:** a short blue link at the end of bullets with public proof. No symbols.
4. **Private work is first-class:** skills from private or local projects always appear. Only the link differs.

## Visibility rules

| Project `visibility` | Body shows | Evidence page shows |
| --- | --- | --- |
| `public` (+ `url`) | Bullet + blue link (commit, PR or project URL) | Link |
| `private` | Bullet + *(private repository)* | "private repository" |
| `local` or unset | Bullet only | "local work" |

Spokes never send repository URLs. Only the hub's `profile.yaml` knows a project's URL, and only when marked public. Because visibility lives on the project and links are resolved at build time, making a repo public later adds links to every past card without re-capture.

## Proof levels (computed, never typed)

| Level | Rule |
| --- | --- |
| `public` | At least one resolvable public link (public project, card `lnk`, or a link in `vault/links.jsonl`) |
| `confirmed` | Publication with a DOI (BibTeX/ORCID) |
| `captured` | `src` is `claude_session`, `git_commit` or `watcher` |
| `self-reported` | `src` is `manual` or `import` |

## Components

| Unit | Responsibility |
| --- | --- |
| `compile/evidence.py` | Repo URL normalisation, commit URLs per host (GitHub, GitLab, Bitbucket), proof resolution per card and per bullet, link checking (injectable fetcher) |
| `compile/verify.py` | Manifest (PDF SHA-256, per-bullet proof), static verify page, QR code, publish to a git repo, `verify` comparison |
| `capture/projects.py` | Device path → project mapping; tagging captured cards with `ctx` |
| CLI | `project set/map/list`, `link`, `log --link`, `build --check-links --publish`, `verify` |
| Renderers | Blue links in PDF (RenderCV `colors.links`), DOCX (hyperlink runs) and Markdown; *(private repository)* label; Evidence section; "Verify" header link |

## Data changes

- Card: optional `lnk` (list of https URLs, max 5, not part of the ID hash).
- Profile `projects[]`: `visibility`, `url`. Profile `verify`: `{repo, path, url}`.
- Device: `projects: [{ctx, path}]`.
- Hub: `vault/links.jsonl` (append-only `{id, url, t}`).
- Build: `build.json` gains `pdf_sha256`; `manifest.json` lists every bullet with cites, level and link.

## Honesty and limits

- Links are never invented: they come from a public project's real commit reference, a URL the user supplied, or a DOI.
- The fingerprint proves the PDF was not altered after the build. It does not prove claims true, and the verify page says so.
- The QR code ships on the verify page and in DOCX first. In-PDF QR needs a custom RenderCV theme (follow-up).
- The Evidence page is an appendix: the page limit for the CV body is `limits.pages`, and the build allows one extra page for the appendix.

## Testing

Unit tests for every unit above, an end-to-end build with mixed public/private/local projects, publish + verify against a local bare repo, and a visual check of the demo PDF.
