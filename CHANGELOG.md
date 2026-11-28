# Changelog

## 1.4.0 (2026-11-28)

- **Windows without installing Python:** every release now includes `cvprism-windows.zip`, with the official embeddable Python and everything cvprism needs. Unzip it and double-click **Open cvprism**. CI builds and runs it like a user would before it's published ([ADR-019](docs/adr/ADR-019-windows-bundle.md)).
- **Scan-to-verify QR code in the PDF:** when a verify page is configured, a small QR code in the CV header links to it, next to a "Verify this CV" link.

## 1.3.0 (2026-11-28)

### The cvprism app: no terminal needed ([ADR-018](docs/adr/ADR-018-local-app.md))
- `cvprism app` opens a local app in your browser: add evidence in plain language, upload a LinkedIn export or old CV, set project visibility, see your evidence and its proof level, and build CVs for a role or a pasted job posting, with downloads and the ATS, gap and quality reports on one page.
- Double-clicking `start.bat` / running `start.sh` with no arguments now sets up in the browser and opens the app.
- Runs on 127.0.0.1 only, behind a one-time key, CSRF tokens, a Host check and a strict content-security policy; no JavaScript.

## 1.2.0 (2026-11-28)

### Recruiter-ready output ([ADR-016](docs/adr/ADR-016-recruiter-ready.md))
- **No repetition:** repeated opening verbs are varied with vetted synonyms, and near-duplicate lines are merged (the stronger proof wins).
- **No filler:** weak openers, buzzwords and over-long lines are reported in `quality.md`. The Claude drafting prompt now asks for challenge → action → result lines with specific verbs.
- **ATS read-back:** every build re-reads its own PDF/Word file like an ATS (contacts first, standard headings, every line readable, links visible as text, size) and writes `ats.md`. Job-posting builds add a keyword-match score with opportunities vs. gaps.

### Signed builds and an open standard ([ADR-017](docs/adr/ADR-017-signed-builds-open-spec.md))
- `cvprism build --sign` signs the manifest with your existing SSH key; `cvprism verify --github <user>` checks it against GitHub's published keys.
- The evidence-linked CV format is published as an open specification with a JSON Schema: `docs/spec/evidence-linked-cv-v1.md`.

## 1.1.0 (2026-11-28)

### Verifiable CVs
- Lines with public proof end with a short **blue link** to the work itself (commit, PR, project, DOI, PyPI, video). The visible text is the URL, so the CV stays ATS-safe.
- **Private work keeps its skills:** lines from private repositories show *(private repository)*; local work shows no label. Nothing is hidden or downgraded.
- Every line gets a computed **proof level** (public proof, third-party confirmed, captured, self-reported), listed on a final **Evidence** page in PDF, Word and Markdown.
- `cvprism project set/map/list`: mark projects public, private or local once; tag folders on each computer.
- `cvprism log --link` and `cvprism link <card> <url>` for proof outside git.
- `cvprism build --check-links` drops dead links; `--publish` pushes a verify page (evidence table, QR code, file fingerprint) to your own GitHub Pages; `cvprism verify` checks a CV file against it.
- Design: [ADR-015](docs/adr/ADR-015-verifiable-cv.md).

## 1.0.0 (2026-11-27)

First public release.

### Capture
- `cvprism log` with Claude-normalised, market-facing wording, or `--raw` offline. Metrics you did not state are never kept.
- Automatic capture from Claude Code sessions (SessionEnd hook), git commits (chaining global hook dispatcher) and opted-in project folders (dependency and tool names only).
- Code-only reducers and a redactor (secret scanners, deny-terms, path/URL/email scrubbing, plugins) before anything reaches an LLM.
- Novelty filter: a new card only for a new skill, a higher depth, a new measurable result, or non-code work.
- `cvprism import-linkedin`, `import-cv`, `import-orcid` to bootstrap from what you already have.

### Sync
- Hub-and-spoke, append-only per-device inboxes, content-hash card IDs: conflict-free over every transport.
- Adapters: private git repo, synced folders (Google Drive, OneDrive, Dropbox), USB drop-box, Syncthing, local folder. Several at once; offline outbox.
- Hub merge with quarantine, `suppress`, `purge`, epochs and `hub promote`; registry flows back to spokes.

### Compile
- `cvprism build --role <role>` and `--jd <file|url>` to PDF (RenderCV/Typst, fitted to the page limit), DOCX and Markdown.
- A deterministic honesty gate: every bullet cites cards, and every number must trace to evidence. `evidence.md`, `rejected.md`, `gaps.md`.
- Five starter roles with `extends` inheritance; market-phrase intel from postings you save.

### Usability
- `start.sh` / `start.bat` from a clone or USB stick; terminal or browser (`cvprism init --web`) setup.
- `cvprism install` / `uninstall` (fully reversible), background agent at login on Windows, macOS and Linux.
- `cvprism demo` builds sample CVs offline in seconds.
