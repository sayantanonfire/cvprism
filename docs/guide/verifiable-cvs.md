# Verifiable CVs

AI made every CV look polished, so recruiters stopped trusting polish. cvprism makes honesty checkable instead: lines with public proof carry a blue link to the work itself, every line is graded by how strong its proof is, and private work keeps its skills without exposing anything.

## What the reader sees

- **In the body:** bullets with public proof end with a short blue link, for example `github.com/you/flood-copilot/commit/9fceb02` or `doi.org/10.1016/…`. The visible text is the real URL (no icons), so it survives ATS parsing.
- **Private work:** ends with *(private repository)*. The skill and the achievement are fully listed; only the code is not public.
- **Local work:** no label at all.
- **Last page, "Evidence":** every line with its proof level, link (or "private repository" / "local work" / "no link yet") and the date it was captured.

| Proof level | Meaning |
| --- | --- |
| Public proof | Anyone can click and see the work |
| Third-party confirmed | Published with a DOI |
| Captured | Recorded automatically at the time (Claude Code session, commit, project folder) |
| Self-reported | You entered it (manual log or import) |

## Mark your projects once

```bash
cvprism project set flood-copilot --public --url https://github.com/you/flood-copilot
cvprism project set client-dam --private --display "Dam-break study for a utility"
cvprism project set thesis-code --local
cvprism project list
```

Visibility lives on the project, so making a repo public later adds links to every past line from it at the next build. Nothing needs re-capturing.

On each computer, tell cvprism which folder belongs to which project, so captured commits and sessions are tagged automatically:

```bash
cvprism project map flood-copilot D:\work\flood-copilot
```

Only the project alias travels between computers. Repository URLs exist only on your hub, and only for projects you mark public.

## Add proof that isn't in git

```bash
cvprism log "Presented flood copilot at EGU 2026" --skill science-communication --depth 5 --work \
  --link https://www.youtube.com/watch?v=...
cvprism link c_9a59b3fedb34160f https://pypi.org/project/hydrotools/
```

Links must be public `https://` addresses. Publications from BibTeX/ORCID link through their DOI automatically.

## Build with proof

```bash
cvprism build --role applied-ai --check-links
```

`--check-links` opens every link first and drops any that don't load, so you never send a dead link.

## Publish a verify page (optional)

Add a target to `profile.yaml`: a public GitHub Pages repository you own.

```yaml
verify:
  repo: git@github.com:you/you.github.io.git
  path: cv
  url: https://you.github.io/cv
```

Then build with `--publish`. cvprism writes a small page (evidence table, QR code, file fingerprint) and pushes it to that repository. Your CV gets a "Verify this CV" link in the header, and the Word file includes the QR code.

Anyone can confirm a CV file is exactly the one you built:

```bash
cvprism verify cv.pdf --manifest https://you.github.io/cv/manifest.json
```

!!! note "What the fingerprint proves"
    The fingerprint proves the file was not changed after cvprism built it. It does not prove the claims: the public links do that. The verify page says this in plain words.

## Why this design

See [ADR-015](../adr/ADR-015-verifiable-cv.md) and the [design spec](../superpowers/specs/2026-11-28-verifiable-cv-design.md).
