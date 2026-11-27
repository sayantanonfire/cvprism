# sync

The per-device outbox (`~/.cvprism/outbox/<device-id>/YYYY-MM.jsonl`), per-adapter replication cursors and the scheduler that pushes to every available adapter and pulls the newest registry. See [docs/SYNC.md](../../docs/SYNC.md) for the invariants every adapter must keep.
