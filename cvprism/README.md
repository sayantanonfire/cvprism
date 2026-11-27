# cvprism (Python package)

The installable package behind the `cvprism` CLI. Subpackages map one-to-one to the components in [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md#-components): `capture` (signals to candidate cards), `novelty` (registry and filter), `sync` (outbox and adapters), `hub` (merge and publish) and `compile` (CV generation). JSON Schemas live in `schemas/` from M1. Phase 0: placeholder only, no code yet.
