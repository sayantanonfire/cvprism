# Contributing to cvprism

Thanks for helping. cvprism is built so most contributions need no changes to its core.

## Ways to contribute

| Contribution | Where | Needs code? |
| --- | --- | --- |
| A role profile | `cvprism/data/roles/<id>.yaml` | No. Copy a starter and edit it. Schema in `docs/SCHEMA.md` |
| Skill names and aliases | `cvprism/data/seed_skills.json` | No. Add `{name, cat, aliases, parent}` |
| A sync adapter | a module implementing `available/push/pull/status` | Yes. It must pass `tests/unit/test_sync_conformance.py` |
| A design change | a new ADR in `docs/adr/` | Discuss in an issue first |

Third-party adapters can live in their own package and register through the `cvprism.adapters` entry-point group.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev,all]"      # Windows: .venv\Scripts\pip
.venv/bin/python -m pytest
```

Rules of the house:

- **Tests first.** Every behaviour change starts with a failing test.
- **Never commit personal data.** `*.jsonl` outside `tests/fixtures/` is git-ignored for a reason. Fixtures use synthetic people only.
- **Privacy boundary.** Capture code may keep names, counts and the user's own words, never file contents, tool output, diffs or data (see `docs/SECURITY_PRIVACY.md`).
- **Honesty gate.** Nothing may add a claim or number to a CV that the evidence doesn't support.
- **Cross-platform.** CI runs Windows, macOS and Linux on Python 3.10 and 3.13.
- Regenerate the CLI reference when you change commands: `typer cvprism.cli utils docs --name cvprism --title "CLI reference" --output docs/guide/cli.md`.

## Commit and PR style

Conventional-style subjects (`feat(sync): ...`, `fix(compile): ...`). One logical change per commit. PRs describe what changed, why, and how it was tested.
