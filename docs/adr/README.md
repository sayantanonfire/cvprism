# Architecture Decision Records

Each ADR records one non-obvious choice: its context, the decision, the alternatives and the consequences. ADRs are immutable once **Accepted**. To change a decision, write a new ADR that supersedes it.

| ADR | Title | Status |
| --- | --- | --- |
| [001](ADR-001-hub-spoke-append-only.md) | Hub-and-spoke topology with append-only per-device inboxes | Proposed |
| [002](ADR-002-content-hash-ids.md) | Card IDs hash canonical fields, not free text | Proposed (amends kickoff spec) |
| [003](ADR-003-plain-files-compact-jsonl.md) | Plain files; compact-key JSONL for cards only | Proposed |
| [004](ADR-004-local-outbox.md) | Local outbox is the source of truth; spokes hold no vault | Proposed (amends kickoff spec) |
| [005](ADR-005-adapter-interface.md) | Adapter interface and whole-file atomic replication | Proposed |
| [006](ADR-006-syncthing-not-custom-lan.md) | Syncthing instead of a custom LAN server | Proposed |
| [007](ADR-007-extraction-via-claude-cli.md) | Hooks only enqueue; extraction via headless `claude -p` over a code-reduced digest | Proposed (amends kickoff spec) |
| [008](ADR-008-git-hooks-chaining.md) | Global git hooks path with a chaining dispatcher | Proposed (amends kickoff spec) |
| [009](ADR-009-honesty-gate.md) | Deterministic honesty gate for CV bullets | Proposed |
| [010](ADR-010-renderer.md) | RenderCV for PDF, Pandoc for DOCX/MD | Proposed (amends kickoff spec) |
| [011](ADR-011-depth-ladder-novelty.md) | Five-level depth ladder and novelty rules | Proposed |
| [012](ADR-012-hub-epoch.md) | Hub identity and promotion via epochs | Proposed |
| [013](ADR-013-install-and-service.md) | Venv in the user data dir; OS-native login services | Proposed |
| [014](ADR-014-v1-scope.md) | What v1.0 deliberately leaves out | Accepted |
| [015](ADR-015-verifiable-cv.md) | Verifiable CV through project-level visibility and computed proof levels | Accepted |

Template: Context → Decision → Alternatives considered → Consequences.
