# ADR-008: Global git hooks path with a chaining dispatcher

- **Status:** Proposed. This **amends** the kickoff spec ("git post-commit hook (global hooks path)").
- **Date:** 2026-11-27

## Context

Setting `git config --global core.hooksPath` makes git **ignore every repository's own `.git/hooks/`**. It also replaces any hooks path the user already set globally. Users of pre-commit, husky or lefthook would silently lose their hooks, which would kill adoption. Repos that set a *local* `core.hooksPath` (husky does) override the global one, so cvprism would never see their commits.

## Decision

- Install a dispatcher directory `~/.cvprism/git-hooks/` containing a script **for every client-side hook name**. Each script:
  1. runs cvprism's handler (for `post-commit` only),
  2. then runs the repo-local `$GIT_DIR/hooks/<name>` if present and executable,
  3. then runs the previous global hooks path's `<name>` if one was set before install,
  4. and propagates exit codes for blocking hooks (`pre-commit`, `commit-msg`, `pre-push`).
- Record the previous `core.hooksPath` in `device.yaml` and restore it exactly on uninstall.
- For repos with a local `core.hooksPath`, `cvprism doctor` lists them and offers an opt-in per-repo shim.
- cvprism's own handler never blocks a commit: it enqueues and always exits 0.

## Consequences

Existing tooling keeps working. Repos using husky and similar need a one-time opt-in, which is documented.
