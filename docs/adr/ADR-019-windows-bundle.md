# ADR-019: A no-install Windows download built from the official embeddable Python

- **Status:** Accepted (refines ADR-013)
- **Date:** 2026-11-28

## Context

The cvprism app (ADR-018) removed the terminal, but non-developers on Windows still had to install Python first. ADR-013 rejected PyInstaller (large, antivirus false positives).

## Decision

Each release attaches `cvprism-windows.zip`, built on GitHub Actions:

- It contains the **official python.org embeddable distribution** (unmodified, PSF licence), with its `._pth` file pointing at a bundled `lib\` folder holding cvprism and all dependencies, including the PDF and Word extras.
- It ships two launchers: `Open cvprism.bat` (setup in the browser, then the app) and `cvprism.bat` (the command line).
- CI builds and **smoke-tests the bundle as a user would**: init, log, a full demo build with 4 PDFs, and doctor. This runs on every pull request and again before the zip is attached to a release.

## Alternatives considered

- **PyInstaller / Nuitka single exe:** antivirus false positives and opaque binaries.
- **An MSI installer:** needs code signing to avoid SmartScreen warnings; possible later.
- **winget / Microsoft Store:** good follow-ups once there are users asking.

## Consequences

The download is larger than the source (around 60–90 MB, mostly the Typst engine and fonts). The folder must stay in place after first use, because hooks and the login agent point into it; `READ ME FIRST.txt` says so. macOS and Linux keep using `start.sh` with the system Python.
