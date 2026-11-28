# Getting started

!!! tip "No terminal?"
    Double-click `start.bat` (Windows) or run `./start.sh` with no arguments. Setup and the [cvprism app](app.md) open in your browser.

You need **Python 3.10+** (3.12+ for PDF output) and, for automatic capture, **Claude Code**. There is no database and no server.

## Install

```bash
git clone https://github.com/sayantanonfire/cvprism.git
cd cvprism
./start.sh          # Windows: start.bat
```

The start script creates a private Python environment in your user data folder, installs cvprism, and starts setup. It works the same from a USB stick: once installed, nothing depends on the stick.

Setup asks four things: a device name, whether this computer is the **hub** (where CVs are built) or a **spoke**, where your private vault lives, and which project folders to watch. Prefer a browser page? Run `cvprism init --web`.

!!! warning "Your vault is private"
    The vault holds your career evidence. Keep it outside the cvprism code folder. cvprism refuses to create it there.

## Bring in what you already have

```bash
cvprism import-linkedin ~/Downloads/Basic_LinkedInDataExport.zip   # positions, education, certifications, skills
cvprism import-cv ~/Documents/old_cv.docx                          # bullets become cards
cvprism import-orcid 0000-0002-1825-0097                           # publications into pubs.bib
```

Imported cards are flagged for review, because they are self-reported. Skills that were only listed on LinkedIn become depth-1 cards: cvprism knows about them, but they don't appear on a CV until you have stronger evidence.

## Turn on automatic capture

```bash
cvprism install --dry-run    # shows every change first
cvprism install              # Claude Code hook, git hook, /cv-log skill, background agent
```

Everything is reversible with `cvprism uninstall`, which restores your previous git and Claude Code settings exactly.

From now on:

- When a Claude Code session ends, a summary of the skills and methods used becomes candidate cards a few minutes later.
- Git commits and new dependencies in watched folders are batched into the same process.
- `/cv-log` inside Claude Code, or `cvprism log "..."` in a terminal, records anything else: papers, talks, field work.

## Build a CV

```bash
cvprism build --role applied-ai
cvprism build --jd https://example.com/jobs/123
```

See [Building CVs](building-cvs.md).
