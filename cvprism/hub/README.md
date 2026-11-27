# hub

Runs only on the hub device. It pulls every inbox from every adapter, validates and quarantines invalid lines, recomputes IDs, unions cards into `vault/cards.jsonl`, rebuilds `vault/registry.json`, and publishes the registry and `hub.json` back through all adapters. It also handles hub promotion and demotion via epochs (ADR-012), `rebuild`, `suppress` and `purge`.
