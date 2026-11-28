# ADR-018: A local, server-rendered browser app for non-developers

- **Status:** Accepted
- **Date:** 2026-11-28

## Context

cvprism's mission needs people who never open a terminal: researchers, field scientists, consultants. The engine is complete; what's missing is a front door.

## Decision

- **`cvprism app`** serves a small web app on `127.0.0.1` using only the standard library (`http.server`). Double-clicking `start.bat`/`start.sh` with no arguments sets up in the browser and opens the app.
- **Server-rendered HTML, no JavaScript.** It's fast, accessible, easy to audit, and allows a strict CSP (`default-src 'none'`).
- **Security:**
  - a one-time key in the URL becomes an HttpOnly, `SameSite=Strict` cookie
  - every form carries a CSRF token
  - the Host header must be localhost (DNS-rebinding defence)
  - all output is escaped
  - uploads are capped at 25 MB, written to a temporary folder, and type-checked by extension
  - downloads are confined to the vault's `build/` folder
- **Same engine:** every page calls the same functions as the CLI, so honesty rules can't diverge.

## Alternatives considered

- **Electron/Tauri desktop app:** a large download and a second toolchain, for little gain.
- **A hosted web app:** contradicts "your data stays on your computers" (ADR-001, ADR-014).
- **A single-page React app:** needs a JS build pipeline and weakens the CSP.

## Consequences

The app must keep running while in use (it says so). Mobile access isn't supported, by design: the server binds to localhost only.
